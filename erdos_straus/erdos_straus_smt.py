#!/usr/bin/env python3
"""
Emit or solve a bounded SMT experiment for Erdos-Straus.

This is intentionally separate from the main arithmetic search. It is useful
for exploring whether a solver-based formulation is competitive for small,
tightly bounded instances.

If z3 is available, the script can solve the instance directly. Otherwise it
can still emit an SMT-LIB2 file for external solvers.
"""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import z3

    HAVE_Z3 = True
except ImportError:
    HAVE_Z3 = False


def build_smt2(n: int, max_x: int, max_y: int, max_z: int) -> str:
    return "\n".join(
        [
            "; Erdos-Straus bounded instance",
            f"; n = {n}",
            "(set-logic QF_NIA)",
            "(declare-const x Int)",
            "(declare-const y Int)",
            "(declare-const z Int)",
            "(assert (<= 1 x))",
            "(assert (<= x y))",
            "(assert (<= y z))",
            f"(assert (<= x {max_x}))",
            f"(assert (<= y {max_y}))",
            f"(assert (<= z {max_z}))",
            f"(assert (= (* 4 x y z) (* {n} (+ (* x y) (* x z) (* y z)))))",
            "(check-sat)",
            "(get-model)",
            "",
        ]
    )


def solve_with_z3(n: int, max_x: int, max_y: int, max_z: int) -> tuple[str, tuple[int, int, int] | None]:
    if not HAVE_Z3:
        raise RuntimeError("z3 is not installed.")

    x = z3.Int("x")
    y = z3.Int("y")
    z = z3.Int("z")

    solver = z3.Solver()
    solver.add(x >= 1, x <= y, y <= z)
    solver.add(x <= max_x, y <= max_y, z <= max_z)
    solver.add(4 * x * y * z == n * (x * y + x * z + y * z))

    result = solver.check()
    if result == z3.sat:
        model = solver.model()
        return "sat", (model[x].as_long(), model[y].as_long(), model[z].as_long())
    if result == z3.unsat:
        return "unsat", None
    return "unknown", None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, required=True, help="Value of n to encode.")
    parser.add_argument("--max-x", type=int, default=100, help="Upper bound for x.")
    parser.add_argument("--max-y", type=int, default=250, help="Upper bound for y.")
    parser.add_argument("--max-z", type=int, default=2_000, help="Upper bound for z.")
    parser.add_argument(
        "--emit-smt2",
        type=Path,
        default=None,
        help="Write the SMT-LIB2 encoding to this file.",
    )
    parser.add_argument(
        "--solve",
        action="store_true",
        help="Attempt to solve directly with z3 if it is installed.",
    )
    args = parser.parse_args()

    smt2 = build_smt2(args.n, args.max_x, args.max_y, args.max_z)
    if args.emit_smt2 is not None:
        args.emit_smt2.write_text(smt2, encoding="ascii")
        print(f"[write] wrote SMT-LIB2 model to {args.emit_smt2}")

    if args.solve:
        if not HAVE_Z3:
            print("[error] z3 is not installed. Install `z3-solver` to use --solve.")
            return 1
        result, model = solve_with_z3(args.n, args.max_x, args.max_y, args.max_z)
        print(f"[solve] result={result}")
        if model is not None:
            x, y, z = model
            print(f"[model] x={x} y={y} z={z}")
        return 0 if result == "sat" else 1

    if args.emit_smt2 is None:
        print(smt2, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
