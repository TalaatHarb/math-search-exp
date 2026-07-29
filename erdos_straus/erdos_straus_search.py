#!/usr/bin/env python3
"""
Search for Erdos-Straus counterexample candidates.

The Erdos-Straus conjecture states that for every integer n >= 2 there exist
positive integers x, y, z such that:

    4 / n = 1 / x + 1 / y + 1 / z

This script uses a small but extensible "reduce -> filter -> verify" pipeline:

1. apply simple congruence identities that instantly construct solutions for
   many n;
2. lift known solutions from proper divisors to composite numbers;
3. run a complete exact search for the remaining survivors.

The filter stage is intentionally structured so stronger residue-class filters
from the literature can be added later without changing the verifier.
"""

from __future__ import annotations

import argparse
import collections
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Decomposition:
    x: int
    y: int
    z: int

    def ordered(self) -> "Decomposition":
        x, y, z = sorted((self.x, self.y, self.z))
        return Decomposition(x, y, z)


@dataclass(frozen=True)
class SearchRecord:
    n: int
    decomposition: Decomposition
    source: str


def verify_decomposition(n: int, decomposition: Decomposition) -> bool:
    x, y, z = decomposition.ordered().__dict__.values()
    if x <= 0 or y <= 0 or z <= 0:
        return False
    return 4 * x * y * z == n * (x * y + x * z + y * z)


def format_decomposition(decomposition: Decomposition) -> str:
    ordered = decomposition.ordered()
    return f"(x={ordered.x}, y={ordered.y}, z={ordered.z})"


def sieve_smallest_prime_factor(limit: int) -> list[int]:
    spf = list(range(limit + 1))
    if limit >= 1:
        spf[1] = 1
    for value in range(2, int(limit**0.5) + 1):
        if spf[value] != value:
            continue
        for multiple in range(value * value, limit + 1, value):
            if spf[multiple] == multiple:
                spf[multiple] = value
    return spf


def distinct_prime_factors(n: int, spf: list[int]) -> list[int]:
    factors: list[int] = []
    while n > 1:
        prime = spf[n]
        factors.append(prime)
        while n % prime == 0:
            n //= prime
    return sorted(set(factors))


def lift_decomposition(scale: int, decomposition: Decomposition) -> Decomposition:
    return Decomposition(
        decomposition.x * scale,
        decomposition.y * scale,
        decomposition.z * scale,
    ).ordered()


def elementary_decomposition(n: int) -> tuple[str, Decomposition] | None:
    if n % 2 == 0:
        return "even", Decomposition(n // 2, n, n).ordered()

    if n % 3 == 0:
        return "divisible-by-3", Decomposition(n // 3, n // 3, n).ordered()

    if n % 3 == 2:
        return "mod-3-eq-2", Decomposition(n, (n + 1) // 3, n * (n + 1) // 3).ordered()

    if n % 4 == 3:
        a = (n + 1) // 4
        return "mod-4-eq-3", Decomposition(a + 1, a * (a + 1), n * a).ordered()

    return None


def exact_search(n: int) -> Decomposition | None:
    """
    Complete search with x <= y <= z.

    For each x, rewrite:

        4/n - 1/x = p/q = 1/y + 1/z

    then iterate y in the complete range implied by y <= z and solve for z.
    """
    x_start = n // 4 + 1
    x_stop = (3 * n) // 4

    for x in range(x_start, x_stop + 1):
        p = 4 * x - n
        q = n * x
        g = math.gcd(p, q)
        p //= g
        q //= g

        y_start = max(x, q // p + 1)
        y_stop = (2 * q) // p
        for y in range(y_start, y_stop + 1):
            numerator = q * y
            denominator = p * y - q
            if denominator <= 0:
                continue
            if numerator % denominator != 0:
                continue
            z = numerator // denominator
            decomposition = Decomposition(x, y, z).ordered()
            if verify_decomposition(n, decomposition):
                return decomposition
    return None


def find_liftable_divisor(
    n: int,
    spf: list[int],
    solutions: dict[int, SearchRecord],
) -> SearchRecord | None:
    for prime in distinct_prime_factors(n, spf):
        if prime in solutions:
            return solutions[prime]
        cofactor = n // prime
        if 1 < cofactor < n and cofactor in solutions:
            return solutions[cofactor]
    return None


def search_range(
    start_n: int,
    max_n: int,
    progress_every: int,
    stop_after: int,
    show_solutions: bool,
) -> list[int]:
    if start_n < 2:
        raise ValueError("start_n must be >= 2.")
    if max_n < start_n:
        raise ValueError("max_n must be >= start_n.")
    if progress_every < 0:
        raise ValueError("progress_every must be >= 0.")
    if stop_after < 1:
        raise ValueError("stop_after must be >= 1.")

    spf = sieve_smallest_prime_factor(max_n)
    solutions: dict[int, SearchRecord] = {}
    filter_counts: collections.Counter[str] = collections.Counter()
    exact_checks = 0
    candidates: list[int] = []

    for n in range(2, max_n + 1):
        if n < start_n:
            known = elementary_decomposition(n)
            if known is not None:
                source, decomposition = known
                solutions[n] = SearchRecord(n, decomposition, source)
                continue

            lifted = None
            if spf[n] != n:
                lifted = find_liftable_divisor(n, spf, solutions)
            if lifted is not None:
                scale = n // lifted.n
                solutions[n] = SearchRecord(
                    n,
                    lift_decomposition(scale, lifted.decomposition),
                    f"lift-from-{lifted.n}",
                )
                continue

            decomposition = exact_search(n)
            if decomposition is not None:
                solutions[n] = SearchRecord(n, decomposition, "exact-search")
            continue

        known = elementary_decomposition(n)
        if known is not None:
            source, decomposition = known
            solutions[n] = SearchRecord(n, decomposition, source)
            filter_counts[source] += 1
            if show_solutions:
                print(f"[solution] n={n} source={source} {format_decomposition(decomposition)}")
        else:
            lifted = None
            if spf[n] != n:
                lifted = find_liftable_divisor(n, spf, solutions)
            if lifted is not None:
                scale = n // lifted.n
                decomposition = lift_decomposition(scale, lifted.decomposition)
                source = f"lift-from-{lifted.n}"
                solutions[n] = SearchRecord(n, decomposition, source)
                filter_counts["composite-lift"] += 1
                if show_solutions:
                    print(f"[solution] n={n} source={source} {format_decomposition(decomposition)}")
            else:
                exact_checks += 1
                decomposition = exact_search(n)
                if decomposition is not None:
                    solutions[n] = SearchRecord(n, decomposition, "exact-search")
                    filter_counts["exact-search"] += 1
                    if show_solutions:
                        print(f"[solution] n={n} source=exact-search {format_decomposition(decomposition)}")
                else:
                    candidates.append(n)
                    print(f"[candidate] n={n} no decomposition found")
                    if len(candidates) >= stop_after:
                        break

        if progress_every and (n - start_n + 1) % progress_every == 0:
            print(
                "[progress] "
                f"n={n:,} checked={n - start_n + 1:,} "
                f"exact_checks={exact_checks:,} candidates={len(candidates):,}"
            )

    print("[summary] filter counts")
    for name in sorted(filter_counts):
        print(f"  {name}: {filter_counts[name]:,}")
    print(
        "[done] "
        f"range={start_n:,}..{min(max_n, n):,} "
        f"exact_checks={exact_checks:,} "
        f"candidates={len(candidates):,}"
    )
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-n",
        type=int,
        default=2,
        help="Smallest n to check (default: 2).",
    )
    parser.add_argument(
        "--max-n",
        type=int,
        default=1_000,
        help="Largest n to check (default: 1000).",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1_000,
        help="Print progress every N tested values (default: 1000).",
    )
    parser.add_argument(
        "--stop-after",
        type=int,
        default=1,
        help="Stop after this many candidate counterexamples are found (default: 1).",
    )
    parser.add_argument(
        "--show-solutions",
        action="store_true",
        help="Print every found decomposition instead of only summaries.",
    )
    args = parser.parse_args()

    candidates = search_range(
        start_n=args.start_n,
        max_n=args.max_n,
        progress_every=args.progress_every,
        stop_after=args.stop_after,
        show_solutions=args.show_solutions,
    )
    return 1 if candidates else 0


if __name__ == "__main__":
    raise SystemExit(main())
