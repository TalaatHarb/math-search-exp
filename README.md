# math-search-exp

Experiments in **counterexample hunting** for hard math conjectures by combining:

- recent structural reductions from the literature,
- aggressive pruning of the search space,
- brute-force verification, and
- SAT/SMT-style encodings when the problem is naturally finite.

## Current state

The repo now has three experiment tracks:

- `beal\` for Beal's conjecture
- `erdos_straus\` for Erdos-Straus counterexample search
- `union_closed\` for Frankl's union-closed sets conjecture

## Beal's conjecture

This repo currently explores **Beal's conjecture**:

> If `A^x + B^y = C^z` with positive integers `A,B,C,x,y,z` and `x,y,z > 2`, then `A,B,C` must share a common prime factor.

There are two scripts:

- `beal\beal_search.py`  
  A two-stage search:
  1. scan curated or locally generated `abc`-style triples `a + b = c`,
  2. fall back to a direct modular-sieve search over small bases and exponents.
- `beal\beal_stream_search.py`  
  Stream very large `c a` files where `b = c - a`, and test whether `a`, `b`, and `c` are all perfect powers.

Large local datasets are intentionally ignored by git:

- `beal\big_triples`
- `beal\triples_below_1018_revised`

## Running the existing experiments

From the repo root on Windows:

```powershell
.venv\Scripts\python.exe beal\beal_search.py --abc-limit 200 --skip-sieve
.venv\Scripts\python.exe beal\beal_stream_search.py --input beal\triples_below_1018_revised --max-lines-per-file 1000
```

## Erdos-Straus starter implementation

This repo now includes a first-pass **Erdos-Straus** search workflow for:

> `4 / n = 1 / x + 1 / y + 1 / z`

Files:

- `erdos_straus\erdos_straus_search.py`
  - applies simple modular/congruence solution filters,
  - lifts known solutions from proper divisors to composites,
  - runs an exact verifier on remaining survivors.
- `erdos_straus\erdos_straus_smt.py`
  - emits a bounded SMT-LIB2 model,
  - optionally solves it with `z3-solver` if that package is installed.

Example commands:

```powershell
.venv\Scripts\python.exe erdos_straus\erdos_straus_search.py --max-n 500
.venv\Scripts\python.exe erdos_straus\erdos_straus_search.py --start-n 2 --max-n 200 --show-solutions
.venv\Scripts\python.exe erdos_straus\erdos_straus_smt.py --n 13 --emit-smt2 erdos13.smt2
```

Current implementation notes:

- the arithmetic path is the primary engine;
- the SMT file is intentionally an experiment for **small bounded instances**;
- the modular filter layer is designed to accept stronger residue filters later.

## Frankl union-closed starter implementation

This repo now also includes a first-pass bounded search workflow for:

> Every finite non-empty union-closed family contains an element that belongs to at least half of its sets.

Files:

- `union_closed\union_closed_search.py`
  - encodes a family as one Boolean variable per subset of `[n]`,
  - enforces exact union-closure and failure of the abundance condition,
  - keeps the search on an active universe by forcing the full set to be present,
  - adds optional symmetry breaking and optional pairwise-separation constraints,
  - can emit an exact SMT-LIB2 instance for a fixed `(n, |F|)` bound.

Example commands:

```powershell
.venv\Scripts\python.exe union_closed\union_closed_search.py --ground-size 5
.venv\Scripts\python.exe union_closed\union_closed_search.py --ground-size 6 --family-size 20 --require-separating
.venv\Scripts\python.exe union_closed\union_closed_search.py --ground-size 6 --family-size 20 --emit-smt2 union_closed_6_20.smt2
```

Current implementation notes:

- this is a **bounded finite search** experiment, not a complete attack on the conjecture;
- the default encoding is solver-first, matching the SAT/CSP direction suggested in the roadmap;
- the optional separation constraint is a search heuristic, so it is off by default.

## Is Beal the right target?

**Probably not as the main long-term target.**

It is still useful as a prototype because it has a clear pipeline:

1. import a mathematically meaningful reduced search space,
2. filter cheaply,
3. verify exactly.

But as a discovery project, Beal has two problems:

- it has already been searched very heavily,
- even after pruning, the surviving arithmetic space is still enormous.

So Beal is a good **framework test**, but not the most promising place to expect a surprise.

## Better next conjectures

| Conjecture | Why it fits this repo | Best search style | Recommendation |
| --- | --- | --- | --- |
| **Erdos-Straus conjecture** (`4/n = 1/x + 1/y + 1/z`) | Very strong modular filtering; recent work keeps shrinking the residue classes that need checking and has pushed verification extremely far. | Residue-class pruning + brute-force batch verification | **Best next step if you want to stay in number theory.** |
| **Frankl's union-closed sets conjecture** | Recent work studies necessary properties of a minimal counterexample; the search is finite after heavy symmetry breaking. | SAT/CSP + canonicalization | **Best next step if you want a solver-native project.** |
| **Hadwiger-Nelson problem** (`chi(R^2) <= 5?`) | Recent computer-assisted work keeps improving finite unit-distance graph searches; SAT is already central for colorability certificates. | Graph generation + SAT | Best stretch goal if you want combinatorics/geometry instead of arithmetic. |

## Short assessment of each direction

### 1. Erdos-Straus conjecture

Why it is attractive:

- it is an explicit **counterexample search** problem,
- modular filters dramatically reduce the candidates,
- the remaining work parallelizes cleanly,
- recent verification work has extended the checked range to very large bounds.

Why it fits better than Beal:

- the reduction machinery is sharper,
- the computational story is cleaner,
- you can measure progress by residue classes, bounds, and batch completion.

If this repo wants a **Beal-like but stronger** follow-up, this is the best choice.

### 2. Frankl's union-closed sets conjecture

Why it is attractive:

- minimal-counterexample reasoning can shrink the space before search,
- SAT/CSP encodings are natural,
- symmetry breaking and canonical forms matter a lot, which makes it a good solver project.

Why it is different from Beal:

- less raw number theory,
- more finite combinatorial search,
- better match for SAT than direct exponent equations.

If the goal is to build a real **SAT-first** counterexample engine, this is the strongest candidate.

### 3. Hadwiger-Nelson problem

Why it is attractive:

- finite graph certificates are possible,
- SAT is already useful for proving non-5-colorability of candidate unit-distance graphs,
- recent work keeps improving the known constructions and search tooling.

Main caveat:

- geometry is the bottleneck, not just satisfiability.

This is exciting, but it is a more ambitious jump than Erdos-Straus or union-closed sets.

## Lower-priority ideas

- **Erdos-Moser equation**: interesting, but current lower bounds and congruence obstructions make a practical counterexample hunt feel less promising than Erdos-Straus.
- **Circulant Hadamard conjecture**: historically very SAT-friendly, but a 2023 claimed proof means it may no longer be the right exploratory target.

## My recommendation

1. **Next arithmetic project:** extend `erdos_straus\` with stronger literature-based residue filters, residue-class generation, and distributed verification.
2. **Next SAT project:** build `union_closed\` and encode minimal-counterexample constraints with aggressive symmetry breaking.
3. Keep the Beal code as the template for the overall workflow: **reduce -> filter -> verify**.

## Suggested repo roadmap

- `beal\` keep as the baseline prototype.
- `erdos_straus\` now contains a starter verifier; next add stronger residue filters and batch generators.
- `union_closed\` now contains a bounded SMT search; next add stronger minimal-counterexample reductions, canonical family generation, and CNF export / SAT runner glue.
- `notes\` is probably unnecessary; keep the repo code-first unless you later want benchmark data or result logs.

## References for the next round

- Erdos-Straus recent verification: `https://arxiv.org/abs/2509.00128`
- Union-closed sets recent finite-reduction work: `https://arxiv.org/abs/2503.00277`
- Union-closed/Reimer-related counterexample structure: `https://arxiv.org/abs/2405.10639`
- Hadwiger-Nelson research repo: `https://github.com/owenpkent/hadwiger-nelson`
- Hadwiger-Nelson overview / computational history: `https://michaelnielsen.org/polymath/index.php?title=Hadwiger-Nelson_problem`
- Circulant Hadamard claimed proof: `https://arxiv.org/abs/2302.08346`

## Bottom line

If the question is **"what should I try next if I want a plausible reduce-then-search project?"**, the answer is:

- **Erdos-Straus** for arithmetic search,
- **Frankl union-closed** for SAT search.
