#!/usr/bin/env python3
"""
Search for bounded counterexample candidates to Frankl's union-closed sets conjecture.

The conjecture states that every finite non-empty union-closed family contains
an element that appears in at least half of its sets.

This script performs a solver-backed finite search over families on an active
ground set of size n. A family is represented by one Boolean variable for each
subset of [n], and the search enforces:

1. union-closure: if A and B are in the family, then A ∪ B is too;
2. abundance failure: every element appears in strictly fewer than half of the
   sets;
3. active universe: the full ground set is present, so the search is really
   over families whose union is exactly [n];
4. optional symmetry breaking by requiring element frequencies to be sorted,
   and optional pairwise separation constraints.

This is meant as a bounded "reduce -> encode -> verify" experiment in the same
spirit as the rest of the repo. It is not a proof engine, but it is a useful
way to test finite search ideas and export exact SMT instances.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import z3

    HAVE_Z3 = True
except ImportError:
    HAVE_Z3 = False


@dataclass(frozen=True)
class SearchResult:
    ground_size: int
    family_size: int
    family: tuple[int, ...]
    element_counts: tuple[int, ...]


def format_subset(mask: int, ground_size: int) -> str:
    members = [str(index + 1) for index in range(ground_size) if mask & (1 << index)]
    return "{" + ", ".join(members) + "}" if members else "{}"


def iter_subsets(ground_size: int) -> range:
    return range(1 << ground_size)


def element_count(family: Iterable[int], element: int) -> int:
    bit = 1 << element
    return sum(1 for mask in family if mask & bit)


def is_union_closed(family: set[int]) -> bool:
    return all((a | b) in family for a in family for b in family)


def verify_family(
    family: tuple[int, ...],
    ground_size: int,
    expected_family_size: int,
    require_separating: bool,
) -> tuple[bool, str]:
    family_set = set(family)
    if len(family) != expected_family_size:
        return False, "decoded family size does not match the requested bound"
    if len(family_set) != len(family):
        return False, "family contains duplicate subsets"
    if not family:
        return False, "family is empty"

    top = (1 << ground_size) - 1
    if top not in family_set:
        return False, "active universe constraint violated: full set missing"
    if not is_union_closed(family_set):
        return False, "family is not union-closed"

    for element in range(ground_size):
        count = element_count(family, element)
        if 2 * count >= len(family):
            return False, f"element {element + 1} is present in at least half the family"

    if require_separating:
        for left in range(ground_size):
            for right in range(left + 1, ground_size):
                if not any(bool(mask & (1 << left)) ^ bool(mask & (1 << right)) for mask in family):
                    return False, f"elements {left + 1} and {right + 1} are not separated"

    return True, "ok"


def build_solver(
    ground_size: int,
    require_separating: bool,
    use_symmetry_breaking: bool,
):
    if not HAVE_Z3:
        raise RuntimeError("z3 is not installed. Install `z3-solver` to use this script.")

    subsets = list(iter_subsets(ground_size))
    members = {mask: z3.Bool(f"subset_{mask:0{ground_size}b}") for mask in subsets}
    family_size = z3.Sum([z3.If(members[mask], 1, 0) for mask in subsets])

    solver = z3.Solver()
    solver.add(family_size >= 1)

    top = (1 << ground_size) - 1
    solver.add(members[top])

    for left in subsets:
        left_var = members[left]
        for right in subsets:
            solver.add(z3.Implies(z3.And(left_var, members[right]), members[left | right]))

    element_counts = []
    for element in range(ground_size):
        bit = 1 << element
        count = z3.Sum([z3.If(members[mask], 1, 0) for mask in subsets if mask & bit])
        element_counts.append(count)
        solver.add(2 * count <= family_size - 1)

    if use_symmetry_breaking:
        for left in range(ground_size - 1):
            solver.add(element_counts[left] >= element_counts[left + 1])

    if require_separating:
        for left in range(ground_size):
            for right in range(left + 1, ground_size):
                separating_sets = [
                    members[mask]
                    for mask in subsets
                    if bool(mask & (1 << left)) ^ bool(mask & (1 << right))
                ]
                solver.add(z3.Or(*separating_sets))

    return solver, members, family_size, tuple(element_counts)


def decode_model(
    model: "z3.ModelRef",
    members: dict[int, "z3.BoolRef"],
    ground_size: int,
) -> tuple[int, ...]:
    family = [mask for mask in iter_subsets(ground_size) if z3.is_true(model.eval(members[mask], model_completion=True))]
    family.sort(key=lambda mask: (mask.bit_count(), mask))
    return tuple(family)


def count_elements(family: tuple[int, ...], ground_size: int) -> tuple[int, ...]:
    return tuple(element_count(family, element) for element in range(ground_size))


def report_result(result: SearchResult) -> None:
    print("\n" + "!" * 72)
    print("COUNTEREXAMPLE CANDIDATE FOUND -- VERIFY INDEPENDENTLY BEFORE TRUSTING THIS.")
    print(f"  ground_size={result.ground_size} family_size={result.family_size}")
    print(
        "  element counts="
        + ", ".join(
            f"e{index + 1}:{count}" for index, count in enumerate(result.element_counts)
        )
    )
    print("  family:")
    for mask in result.family:
        print(f"    {format_subset(mask, result.ground_size)}")
    print("!" * 72)


def search_ground_size(
    ground_size: int,
    min_family_size: int,
    max_family_size: int,
    require_separating: bool,
    use_symmetry_breaking: bool,
    progress: bool,
) -> SearchResult | None:
    solver, members, family_size_expr, _ = build_solver(
        ground_size=ground_size,
        require_separating=require_separating,
        use_symmetry_breaking=use_symmetry_breaking,
    )

    for family_size in range(min_family_size, max_family_size + 1):
        solver.push()
        solver.add(family_size_expr == family_size)
        result = solver.check()
        if progress:
            print(f"[search] ground_size={ground_size} family_size={family_size} result={result}")
        if result == z3.sat:
            model = solver.model()
            family = decode_model(model, members, ground_size)
            ok, reason = verify_family(
                family=family,
                ground_size=ground_size,
                expected_family_size=family_size,
                require_separating=require_separating,
            )
            if not ok:
                raise RuntimeError(f"solver produced an invalid candidate: {reason}")
            return SearchResult(
                ground_size=ground_size,
                family_size=family_size,
                family=family,
                element_counts=count_elements(family, ground_size),
            )
        solver.pop()

    return None


def emit_smt2(
    path: Path,
    ground_size: int,
    family_size: int,
    require_separating: bool,
    use_symmetry_breaking: bool,
) -> None:
    solver, _, family_size_expr, _ = build_solver(
        ground_size=ground_size,
        require_separating=require_separating,
        use_symmetry_breaking=use_symmetry_breaking,
    )
    solver.add(family_size_expr == family_size)
    path.write_text(solver.to_smt2(), encoding="ascii")
    print(f"[write] wrote SMT-LIB2 model to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ground-size",
        type=int,
        default=5,
        help="Active ground-set size n (default: 5).",
    )
    parser.add_argument(
        "--min-family-size",
        type=int,
        default=1,
        help="Smallest family size to test (default: 1).",
    )
    parser.add_argument(
        "--max-family-size",
        type=int,
        default=None,
        help="Largest family size to test (default: all sizes up to 2^n).",
    )
    parser.add_argument(
        "--family-size",
        type=int,
        default=None,
        help="Search only this exact family size.",
    )
    parser.add_argument(
        "--require-separating",
        action="store_true",
        help="Also require the family to separate every pair of elements.",
    )
    parser.add_argument(
        "--disable-symmetry-breaking",
        action="store_true",
        help="Disable element-frequency ordering constraints.",
    )
    parser.add_argument(
        "--emit-smt2",
        type=Path,
        default=None,
        help="Write the exact bounded instance to this SMT-LIB2 file.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-size progress output.",
    )
    args = parser.parse_args()

    if args.ground_size < 1:
        raise ValueError("ground-size must be >= 1.")

    max_possible_family_size = 1 << args.ground_size
    if args.family_size is not None:
        min_family_size = max_family_size = args.family_size
    else:
        min_family_size = args.min_family_size
        max_family_size = args.max_family_size or max_possible_family_size

    if min_family_size < 1:
        raise ValueError("family sizes must be >= 1.")
    if max_family_size < min_family_size:
        raise ValueError("max-family-size must be >= min-family-size.")
    if max_family_size > max_possible_family_size:
        raise ValueError("family size cannot exceed 2^ground-size.")

    use_symmetry_breaking = not args.disable_symmetry_breaking

    if args.emit_smt2 is not None:
        if min_family_size != max_family_size:
            raise ValueError("--emit-smt2 requires an exact family size.")
        emit_smt2(
            path=args.emit_smt2,
            ground_size=args.ground_size,
            family_size=min_family_size,
            require_separating=args.require_separating,
            use_symmetry_breaking=use_symmetry_breaking,
        )

    result = search_ground_size(
        ground_size=args.ground_size,
        min_family_size=min_family_size,
        max_family_size=max_family_size,
        require_separating=args.require_separating,
        use_symmetry_breaking=use_symmetry_breaking,
        progress=not args.quiet,
    )

    if result is not None:
        report_result(result)
        return 1

    print(
        "[done] "
        f"no counterexample found for ground_size={args.ground_size} "
        f"and family sizes {min_family_size}..{max_family_size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
