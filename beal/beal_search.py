#!/usr/bin/env python3
"""
beal_search.py
==============

A search tool for counterexamples to Beal's Conjecture:

    A^x + B^y = C^z   (x, y, z > 2, all positive integers)
    =>  gcd(A, B, C) > 1

A counterexample is a solution where gcd(A, B, C) == 1.

No counterexample is expected to be found -- decades of prior search
(Norvig, the ABC@Home / Beal Prize community, etc.) have already ruled
out small ranges. This script exists to demonstrate the *methodology*
described in the writeup: reuse an existing, independently-curated
dataset before brute forcing, then fall back to a modular-sieve search.

STAGE 1 - ABC-triple dataset
----------------------------
The abc conjecture literature already contains large curated tables of
"high quality" triples a + b = c with gcd(a, b) = 1 and rad(abc) small
relative to c. If Beal's conjecture is false, a counterexample is very
likely to be an unusually high-quality abc-triple (since a genuine
A^x+B^y=C^z solution with pairwise coprime bases is automatically a
strong abc-triple candidate). So instead of generating random sums,
we pull from (or, if unreachable, regenerate a local stand-in for)
that dataset and just test each triple for "are a, b, c each perfect
powers with exponent >= 3?".

This script tries a short list of known dataset mirrors first. Network
sandboxes commonly used to run this (including the one this script was
authored in) often only allow a limited domain allow-list, so the
historical ABC@Home archive (abcathome.com / synthese.dwc.knaw.nl /
mersenneforum.org, etc.) may simply be unreachable. If every fetch
attempt fails, the script transparently falls back to *computing* its
own local abc-triple table up to a configurable bound, which is an
honest (if smaller-scale) stand-in for the real dataset. Swap in a
working mirror URL (or point --abc-file at a local copy of the real
dataset) to use the genuine, much larger table.

STAGE 2 - modular-sieve direct search
--------------------------------------
If Stage 1 finds nothing (expected), the script falls back to a direct
search over small prime exponent triples (x, y, z), using a modular
sieve (several large-prime moduli) to cheaply reject the overwhelming
majority of (A, B) pairs before ever computing a full big-integer
power, then exactly verifying any survivors with gmpy2.

Usage
-----
    pip install requests gmpy2 --break-system-packages

    python3 beal_search.py                          # sane small defaults
    python3 beal_search.py --abc-limit 20000 --sieve-base-max 2000

    # Use a real ABC@Home-style dataset file instead of regenerating one
    # (one triple per line, whitespace or comma separated: a b c)
    python3 beal_search.py --abc-file my_abc_triples.txt
"""

import argparse
import gzip
import itertools
import math
import sys
import time
from pathlib import Path

try:
    import gmpy2
    HAVE_GMPY2 = True
except ImportError:
    HAVE_GMPY2 = False

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False


# --------------------------------------------------------------------------
# Small number-theory helpers
# --------------------------------------------------------------------------

def integer_nth_root(n: int, k: int):
    """Return (root, is_exact) for the integer k-th root of n."""
    if n < 0:
        return None, False
    if HAVE_GMPY2:
        root, exact = gmpy2.iroot(n, k)
        return int(root), bool(exact)
    # Fallback: binary search (slower, pure python)
    if n == 0:
        return 0, True
    lo, hi = 0, 1 << ((n.bit_length() // k) + 2)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if mid ** k <= n:
            lo = mid
        else:
            hi = mid - 1
    return lo, lo ** k == n


def perfect_power_decompositions(n: int, min_exp: int = 3, max_exp: int = None):
    """
    All ways to write n = base**exp with exp >= min_exp.
    Returns a list of (base, exp) pairs, largest base (smallest exp) first.
    """
    if n < 4:
        return []
    if max_exp is None:
        max_exp = n.bit_length()  # 2**max_exp > n well before this
    results = []
    for exp in range(min_exp, max_exp + 1):
        if (1 << exp) > n:
            break
        root, exact = integer_nth_root(n, exp)
        if exact and root >= 2:
            results.append((root, exp))
    return results


def gcd3(a: int, b: int, c: int) -> int:
    return math.gcd(math.gcd(a, b), c)


def smallest_prime_factor_sieve(limit: int):
    """Sieve of smallest prime factors up to `limit`, used for fast radicals."""
    spf = list(range(limit + 1))
    for i in range(2, int(limit ** 0.5) + 1):
        if spf[i] == i:  # i is prime
            for j in range(i * i, limit + 1, i):
                if spf[j] == j:
                    spf[j] = i
    return spf


def radical(n: int, spf) -> int:
    """Product of distinct prime factors of n, using a precomputed spf table.
    Requires n to be within the range the spf table was built for."""
    r = 1
    while n > 1:
        p = spf[n]
        r *= p
        while n % p == 0:
            n //= p
    return r


def prime_factor_set(n: int, spf) -> set:
    """Set of distinct prime factors of n, using a precomputed spf table."""
    primes = set()
    while n > 1:
        p = spf[n]
        primes.add(p)
        while n % p == 0:
            n //= p
    return primes


# --------------------------------------------------------------------------
# Stage 1a: try to fetch a real abc-triple dataset
# --------------------------------------------------------------------------

# Known mirrors that *might* host abc-triple data as plain text/csv/gzip.
# Most of the canonical ABC@Home archive lives outside typical sandboxed
# egress allow-lists (abcathome.com, synthese.dwc.knaw.nl, mersenneforum.org),
# so these are best-effort. Add your own known-good mirror URL(s) here or
# pass --abc-url / --abc-file to override.
CANDIDATE_ABC_DATASET_URLS = [
    "https://raw.githubusercontent.com/dotnwat/beals-conjecture/master/data/abc_triples.txt",
]


def try_fetch_abc_dataset(urls, dest: Path, timeout=15) -> bool:
    """Try each URL in turn; return True and write `dest` on first success."""
    if not HAVE_REQUESTS:
        print("[stage1] 'requests' not installed -- skipping remote fetch.")
        return False
    for url in urls:
        try:
            print(f"[stage1] trying {url} ...")
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                dest.write_bytes(resp.content)
                print(f"[stage1] fetched dataset from {url} -> {dest}")
                return True
            print(f"[stage1]   HTTP {resp.status_code}, skipping.")
        except Exception as e:
            print(f"[stage1]   failed ({e.__class__.__name__}: {e}), skipping.")
    return False


def load_abc_triples_from_file(path: Path):
    """Parse a file of 'a b c' (or 'a,b,c') triples, one per line."""
    opener = gzip.open if path.suffix == ".gz" else open
    triples = []
    with opener(path, "rt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.replace(",", " ").split()
            if len(parts) < 3:
                continue
            try:
                a, b, c = int(parts[0]), int(parts[1]), int(parts[2])
            except ValueError:
                continue
            triples.append((a, b, c))
    return triples


# --------------------------------------------------------------------------
# Stage 1b: local fallback generation of high-quality abc-triples
# --------------------------------------------------------------------------

def generate_local_abc_triples(limit: int, min_quality: float = 1.0):
    """
    Regenerate a local stand-in for the abc-triple dataset:
    all a < b, a + b = c <= limit, gcd(a, b) = 1, with
    quality q = log(c) / log(rad(a*b*c)) >= min_quality.

    This is O(limit^2) with fast radical lookups -- fine for limit in the
    low tens of thousands, not intended to compete with the real,
    community-computed ABC@Home archive (which reached 18-digit sums).
    """
    print(f"[stage1] no remote/local dataset available -- generating a local "
          f"abc-triple table up to limit={limit} (this is a stand-in, not "
          f"the real ABC@Home archive).")
    spf = smallest_prime_factor_sieve(limit)

    triples = []
    t0 = time.time()
    for a in range(1, limit // 2 + 1):
        for b in range(a + 1, limit - a + 1):
            c = a + b
            if c > limit:
                break
            if math.gcd(a, b) != 1:
                continue
            primes = prime_factor_set(a, spf) | prime_factor_set(b, spf) | prime_factor_set(c, spf)
            r = 1
            for p in primes:
                r *= p
            if r >= c:
                continue  # quality < 1, not interesting
            q = math.log(c) / math.log(r)
            if q >= min_quality:
                triples.append((a, b, c))
    print(f"[stage1] generated {len(triples)} candidate high-quality triples "
          f"in {time.time() - t0:.1f}s.")
    return triples


# --------------------------------------------------------------------------
# Stage 1c: test abc-triples for a Beal counterexample
# --------------------------------------------------------------------------

def search_abc_triples_for_beal(triples, min_exp=3):
    """
    For each (a, b, c) triple, check whether a, b, c are each a perfect
    power (exponent >= min_exp) in a way that gives a coprime-base Beal
    solution. Returns the first counterexample found, or None.
    """
    checked = 0
    for (a, b, c) in triples:
        checked += 1
        pa = perfect_power_decompositions(a, min_exp)
        if not pa:
            continue
        pb = perfect_power_decompositions(b, min_exp)
        if not pb:
            continue
        pc = perfect_power_decompositions(c, min_exp)
        if not pc:
            continue
        for (A, x), (B, y), (C, z) in itertools.product(pa, pb, pc):
            if x == y == z:
                continue  # Fermat's Last Theorem already forbids this case
            if gcd3(A, B, C) != 1:
                continue
            if A ** x + B ** y == C ** z:
                return (A, x, B, y, C, z)
    print(f"[stage1] checked {checked} abc-triples: no Beal counterexample "
          f"among them (as expected).")
    return None


# --------------------------------------------------------------------------
# Stage 2: modular-sieve fallback search over small prime exponents
# --------------------------------------------------------------------------

def primes_up_to(n):
    sieve = [True] * (n + 1)
    sieve[0:2] = [False, False]
    for i in range(2, int(n ** 0.5) + 1):
        if sieve[i]:
            for j in range(i * i, n + 1, i):
                sieve[j] = False
    return [i for i, is_p in enumerate(sieve) if is_p]


def sieve_search(base_max: int, exp_max: int, moduli):
    """
    Direct search for A^x + B^y = C^z, gcd(A,B,C)=1, x,y,z prime in
    [3, exp_max], A,B,C in [2, base_max].

    Uses `moduli` (a handful of large primes) to filter candidates
    cheaply via modular exponentiation (pow(base, exp, modulus)) before
    ever computing a full big-integer power, then verifies survivors
    exactly.
    """
    exps = [p for p in primes_up_to(exp_max) if p >= 3]
    if not exps:
        print("[stage2] exp_max too small, nothing to search.")
        return None

    print(f"[stage2] modular-sieve search: bases 2..{base_max}, "
          f"exponents {exps}, moduli={moduli}")

    checked_triples = 0
    t0 = time.time()

    for x, y, z in itertools.product(exps, repeat=3):
        if x == y == z:
            continue  # covered by Fermat's Last Theorem

        # Precompute C^z mod each modulus, bucketed by residue, for fast lookup.
        c_tables = []
        for m in moduli:
            table = {}
            for C in range(2, base_max + 1):
                r = pow(C, z, m)
                table.setdefault(r, []).append(C)
            c_tables.append(table)

        for A in range(2, base_max + 1):
            a_pows = [pow(A, x, m) for m in moduli]
            for B in range(A, base_max + 1):  # A<=B, WLOG up to symmetry of roles
                checked_triples += 1
                candidate_Cs = None
                for m, a_pow, table in zip(moduli, a_pows, c_tables):
                    b_pow = pow(B, y, m)
                    target = (a_pow + b_pow) % m
                    hits = set(table.get(target, ()))
                    candidate_Cs = hits if candidate_Cs is None else (candidate_Cs & hits)
                    if not candidate_Cs:
                        break
                if candidate_Cs:
                    for C in candidate_Cs:
                        if gcd3(A, B, C) != 1:
                            continue
                        if A ** x + B ** y == C ** z:
                            return (A, x, B, y, C, z)

    print(f"[stage2] checked ~{checked_triples} (A,B) pairs across exponent "
          f"combinations in {time.time() - t0:.1f}s: no counterexample found.")
    return None


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--abc-file", type=Path, default=None,
                     help="Local file of abc-triples (a b c per line) to use "
                          "instead of fetching/generating.")
    ap.add_argument("--abc-url", action="append", default=[],
                     help="Additional URL(s) to try before the built-in list. "
                          "Can be passed multiple times.")
    ap.add_argument("--abc-limit", type=int, default=6000,
                     help="Bound for local abc-triple generation if no "
                          "dataset can be fetched/loaded (default: 6000).")
    ap.add_argument("--min-quality", type=float, default=1.0,
                     help="Minimum abc quality log(c)/log(rad(abc)) to keep "
                          "when generating locally (default: 1.0, i.e. any "
                          "quality triple; raise e.g. to 1.2 to shrink and "
                          "focus the table).")
    ap.add_argument("--min-exp", type=int, default=3,
                     help="Minimum exponent to test for perfect powers / in "
                          "the sieve stage (default: 3, per the conjecture).")
    ap.add_argument("--sieve-base-max", type=int, default=300,
                     help="Max base value for the Stage 2 modular-sieve "
                          "search (default: 300).")
    ap.add_argument("--sieve-exp-max", type=int, default=13,
                     help="Max exponent (searches all primes from min-exp "
                          "up to this) for Stage 2 (default: 13).")
    ap.add_argument("--skip-sieve", action="store_true",
                     help="Stop after Stage 1 even if nothing is found.")
    args = ap.parse_args()

    print("=" * 72)
    print("Beal's Conjecture counterexample search")
    print("A^x + B^y = C^z, x,y,z > 2, looking for gcd(A,B,C) == 1")
    print("=" * 72)

    # ---------------- Stage 1: get an abc-triple dataset ----------------
    triples = None

    if args.abc_file is not None:
        print(f"[stage1] loading triples from local file {args.abc_file}")
        triples = load_abc_triples_from_file(args.abc_file)
        print(f"[stage1] loaded {len(triples)} triples.")
    else:
        cache = Path("/tmp/abc_triples_cache.txt")
        urls = list(args.abc_url) + CANDIDATE_ABC_DATASET_URLS
        if try_fetch_abc_dataset(urls, cache):
            triples = load_abc_triples_from_file(cache)
            print(f"[stage1] loaded {len(triples)} triples from fetched dataset.")

        if not triples:
            triples = generate_local_abc_triples(args.abc_limit, args.min_quality)

    result = search_abc_triples_for_beal(triples, min_exp=args.min_exp)
    if result:
        report(result)
        return

    if args.skip_sieve:
        print("\n[done] Stage 1 found nothing; --skip-sieve set, stopping.")
        return

    # ---------------- Stage 2: modular-sieve fallback ----------------
    moduli = [1_000_000_007, 999_999_937, 998_244_353]  # a few large primes
    result = sieve_search(args.sieve_base_max, args.sieve_exp_max, moduli)
    if result:
        report(result)
        return

    print("\n[done] No counterexample found in either stage, consistent with "
          "every prior search of Beal's Conjecture. Increase --abc-limit, "
          "--sieve-base-max, and/or --sieve-exp-max to search further "
          "(runtime grows quickly, especially for Stage 2).")


def report(result):
    A, x, B, y, C, z = result
    print("\n" + "!" * 72)
    print("CANDIDATE COUNTEREXAMPLE FOUND -- VERIFY INDEPENDENTLY BEFORE "
          "TRUSTING THIS.")
    print(f"  {A}^{x} + {B}^{y} = {C}^{z}")
    print(f"  gcd({A}, {B}, {C}) = {gcd3(A, B, C)}")
    print(f"  Check: {A**x} + {B**y} = {A**x + B**y}, {C}^{z} = {C**z}")
    print("!" * 72)


if __name__ == "__main__":
    sys.exit(main())
