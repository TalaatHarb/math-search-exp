#!/usr/bin/env python3
"""
Stream-search Beal counterexample candidates from large ABC triplet files.

Input format (per line):
    c a

Interpretation:
    b = c - a
    a + b = c

The script streams rows from one or more files and checks whether a, b, and c
are each perfect powers with exponent >= min_exp (default: 3). For every row
that passes, it tests base-level coprimality combinations:

    a = A^x, b = B^y, c = C^z, x,y,z >= min_exp, gcd(A,B,C) == 1

Any such row is a Beal counterexample candidate.
"""

from __future__ import annotations

import argparse
import functools
import gzip
import math
from pathlib import Path
from typing import Iterable

try:
    import gmpy2

    HAVE_GMPY2 = True
except ImportError:
    HAVE_GMPY2 = False


def integer_nth_root(n: int, k: int) -> tuple[int, bool]:
    if n < 0:
        return 0, False
    if HAVE_GMPY2:
        root, exact = gmpy2.iroot(n, k)
        return int(root), bool(exact)
    if n == 0:
        return 0, True
    lo, hi = 0, 1 << ((n.bit_length() // k) + 2)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if mid**k <= n:
            lo = mid
        else:
            hi = mid - 1
    return lo, lo**k == n


@functools.lru_cache(maxsize=200_000)
def perfect_power_decompositions(n: int, min_exp: int) -> tuple[tuple[int, int], ...]:
    """
    Return all (base, exp) with n == base**exp and exp >= min_exp.
    """
    if n < 4:
        return ()
    out: list[tuple[int, int]] = []
    for exp in range(min_exp, n.bit_length() + 1):
        if (1 << exp) > n:
            break
        root, exact = integer_nth_root(n, exp)
        if exact and root >= 2:
            out.append((root, exp))
    return tuple(out)


def open_text(path: Path):
    return gzip.open(path, "rt") if path.suffix == ".gz" else open(path, "rt")


def iter_rows(path: Path) -> Iterable[tuple[int, int, int, int]]:
    """
    Yield (line_number, c, a, b) from a `c a` file.
    """
    with open_text(path) as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.replace(",", " ").split()
            if len(parts) < 2:
                continue
            try:
                c = int(parts[0])
                a = int(parts[1])
            except ValueError:
                continue
            b = c - a
            yield lineno, c, a, b


def gcd3(x: int, y: int, z: int) -> int:
    return math.gcd(math.gcd(x, y), z)


def find_counterexample_candidates(
    inputs: list[Path],
    min_exp: int,
    progress_every: int,
    max_lines_per_file: int | None,
    verify_row_coprime: bool,
    stop_after: int,
) -> int:
    total_rows = 0
    malformed_or_invalid = 0
    candidates = 0

    for path in inputs:
        print(f"[scan] file={path}")
        file_rows = 0
        for lineno, c, a, b in iter_rows(path):
            if max_lines_per_file is not None and file_rows >= max_lines_per_file:
                break
            file_rows += 1
            total_rows += 1

            if a <= 0 or b <= 0 or c <= 0:
                malformed_or_invalid += 1
                continue

            if verify_row_coprime and math.gcd(a, b) != 1:
                continue

            pa = perfect_power_decompositions(a, min_exp)
            if not pa:
                if progress_every and total_rows % progress_every == 0:
                    print(f"[progress] rows={total_rows:,} candidates={candidates:,}")
                continue
            pb = perfect_power_decompositions(b, min_exp)
            if not pb:
                if progress_every and total_rows % progress_every == 0:
                    print(f"[progress] rows={total_rows:,} candidates={candidates:,}")
                continue
            pc = perfect_power_decompositions(c, min_exp)
            if not pc:
                if progress_every and total_rows % progress_every == 0:
                    print(f"[progress] rows={total_rows:,} candidates={candidates:,}")
                continue

            # a + b = c already holds by construction. We only need at least
            # one exponent/base choice with pairwise-base gcd condition.
            found_for_row = False
            for A, x in pa:
                for B, y in pb:
                    for C, z in pc:
                        if x == y == z:
                            continue
                        if gcd3(A, B, C) != 1:
                            continue
                        print(
                            "[candidate] "
                            f"file={path.name} line={lineno} "
                            f"{A}^{x} + {B}^{y} = {C}^{z} "
                            f"(a={a}, b={b}, c={c})"
                        )
                        candidates += 1
                        found_for_row = True
                        break
                    if found_for_row:
                        break
                if found_for_row:
                    break

            if candidates >= stop_after:
                print(
                    f"[stop] reached stop-after={stop_after}; "
                    f"rows={total_rows:,} candidates={candidates:,}"
                )
                return candidates

            if progress_every and total_rows % progress_every == 0:
                print(f"[progress] rows={total_rows:,} candidates={candidates:,}")

    print(
        "[done] "
        f"rows={total_rows:,} candidates={candidates:,} invalid_rows={malformed_or_invalid:,}"
    )
    return candidates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=[Path("big_triples"), Path("triples_below_1018_revised")],
        help="One or more files in `c a` format (default: big_triples and triples_below_1018_revised).",
    )
    ap.add_argument(
        "--min-exp",
        type=int,
        default=3,
        help="Minimum exponent for perfect powers (default: 3).",
    )
    ap.add_argument(
        "--progress-every",
        type=int,
        default=1_000_000,
        help="Print progress every N streamed rows (default: 1,000,000).",
    )
    ap.add_argument(
        "--max-lines-per-file",
        type=int,
        default=None,
        help="Optional debug cap on lines processed per file.",
    )
    ap.add_argument(
        "--verify-row-coprime",
        action="store_true",
        help="Verify gcd(a,b)==1 per row (off by default for speed).",
    )
    ap.add_argument(
        "--stop-after",
        type=int,
        default=1,
        help="Stop after this many candidates are printed (default: 1).",
    )
    args = ap.parse_args()

    if args.min_exp < 3:
        raise ValueError("min-exp must be >= 3 for Beal's conjecture.")
    if args.stop_after < 1:
        raise ValueError("stop-after must be >= 1.")
    if args.progress_every < 0:
        raise ValueError("progress-every must be >= 0.")

    return 0 if find_counterexample_candidates(
        inputs=args.input,
        min_exp=args.min_exp,
        progress_every=args.progress_every,
        max_lines_per_file=args.max_lines_per_file,
        verify_row_coprime=args.verify_row_coprime,
        stop_after=args.stop_after,
    ) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
