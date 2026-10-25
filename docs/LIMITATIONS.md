# Limitations, Assumptions, and Threats to Validity (`cpp2py`)

This document records the definitive technical limitations, operational assumptions,
and threats to validity for the `cpp2py` source-to-source translator.

Per Rule 5 and Rule 9 of `AGENTS.md`, this document contains **no hand-typed statistics or experimental results**.
All quantitative metrics (agreement rates, mismatch counts, static and dynamic helper ratios, execution timings, and localisation ranks) must be inspected directly from the machine-generated result files cited throughout this document:
- Overall comparative summary: `out/eval1/tables.md` and `out/eval1/tables.csv`
- Machine-readable metrics: `out/eval1/metrics.json`
- Per-test case execution records: `out/eval1/raw.json`
- Wall-clock runtime measurements: `out/eval1/timing.json`
- Localisation fault injection evaluation: `out/eval_loc/localisation_table.md` and `out/eval_loc/localisation_metrics.json`
- Environment and configuration manifest: `out/eval1/manifest.json`

---

## 1. Design-Level Limitations (ARCH §K.3)

The translation architecture is intentionally restricted to provide defensible semantic guarantees for a well-defined integer core:

1. **Restricted Language Subset:** Only a small subset of C++ is accepted. Language constructs outside the grammar defined in ARCH §A.3 (such as floating-point arithmetic, objects, pointers, arrays, templates, and exceptions) are strictly rejected with error diagnostics (e.g. `E4001`, `E4002`) rather than approximated.
2. **Absence of Arrays, Pointers, and Heap:** Memory is restricted to scalar variables in the local activation frame. Pointers, reference types, dynamically allocated memory, and arrays are excluded.
3. **Absence of Global State:** Global variables are unsupported; all computation occurs within function frames starting from `main`.
4. **Intra-Procedural Interval Analysis:** Range analysis operates strictly within single procedure boundaries. Function call boundaries assume conservative type intervals for arguments and return values rather than propagating inter-procedural ranges.
5. **Non-Relational Abstract Domain:** The interval domain tracks independent lower and upper bounds `[lo, hi]` for individual variables. It cannot represent relational constraints between variables (such as linear relations `x < y` or polyhedral domains).
6. **Widening Without Narrowing:** Fixed-point computation over loop back-edges uses widening directly to type bounds (`int_min`, `int_max`) to guarantee termination, without an subsequent narrowing phase.
7. **Recursion Depth:** Python execution is bound by the CPython recursion call stack limit, preventing translation of unbounded recursion patterns.
8. **Undefined Behaviour is Classified, Not Emulated:** Programs triggering undefined behaviour (such as signed overflow under default policy or division by zero) are detected and classified as `UB_EXCLUDED`, never translated into matching host undefined behaviour.
9. **Empirical Equivalence, Not Formal Proof:** Behavioural equivalence between C++ and Python is established through differential testing and cross-validation against the reference compiler, not through mechanical theorem proving.

---

## 2. Foundational Operational Assumptions (ARCH §0, S1–S6)

The correctness guarantees of `cpp2py` rest on the following explicit assumptions:

- **Assumption S1 (Reference Compiler):** The C++ reference implementation is GCC `g++`, compiling with `-std=c++17 -O0`.
- **Assumption S2 (Target Data Model):** Target machine arithmetic assumes standard two's-complement representation with signed 32-bit `int` and signed 64-bit `long long`, parameterized through `TargetModel` (ARCH §E.1).
- **Assumption S3 (I/O Confinement and Determinism):** Programs interact with their environment solely by reading standard input (`std::cin`) and writing to standard output (`std::cout`); execution paths and outputs are deterministic.
- **Assumption S4 (Input Well-Formedness):** Test inputs consist of well-formed, whitespace-separated decimal integers within declared numeric ranges; exhausted or malformed inputs fall outside the operational contract.
- **Assumption S5 (Runtime Environment):** Generated Python code targets standard CPython ≥ 3.10 and relies exclusively on the Python standard library with no external third-party dependencies.
- **Assumption S6 (Equivalence Criterion):** Semantic equivalence is defined as identical standard output character streams (modulo newline normalisation) and identical process exit status codes (e.g. 0) on all inputs free from undefined behaviour.

---

## 3. Compatibility Policy Semantics (ARCH §E.3, §E.5)

C++ and Python semantics diverge in integer arithmetic, necessitating deliberate semantic policies:

- **Truncating Division:** C++ truncates towards zero (e.g. `-7 / 2 = -3`), whereas Python floor division rounds towards negative infinity (`-7 // 2 = -4`). Compatibility helper `_cpp_div` is selectively inserted when operands may have mixed signs.
- **Remainder Sign:** C++ `%` preserves the sign of the dividend (e.g. `-7 % 2 = -1`), whereas Python `%` preserves the sign of the divisor (`-7 % 2 = 1`). Compatibility helper `_cpp_mod` is selectively inserted when the dividend range includes negative values.
- **Signed Integer Overflow Policies:**
  - `assume_no_overflow` (default): Signed overflow is treated as undefined behaviour per the C++ standard. Operations are assumed not to overflow.
  - `wrap`: Emulates modular two's-complement wraparound arithmetic using helpers `_wrap_i32` and `_wrap_i64`.
  - `trap`: Enforces range boundaries by raising runtime exceptions via helpers `_check_i32` and `_check_i64`.

---

## 4. Threats to Validity (ARCH §J.5)

The empirical conclusions drawn from evaluation runs must be interpreted in light of the following threats to validity:

1. **Benchmark Representativeness:** The curated benchmark suite consists of handcrafted algorithmic kernels. While designed to stress sign permutations, boundary conditions, and loop intervals, it does not represent general software engineering corpora.
2. **Synthetic Generator Biases:** The automated differential test generator produces programs according to explicit production probabilities, which may over-represent or under-represent specific expression structures.
3. **Shared Semantic Model:** The reference IR interpreter and code generator share underlying data structures and semantic definitions in Python. Differential testing against GCC `g++` serves as the primary external oracle to mitigate shared misconception bugs.
4. **Host and Timing Noise:** Wall-clock overhead measurements recorded in `out/eval1/timing.json` are subject to operating system scheduling, background processes, and filesystem caching. Accordingly, timing comparisons report median values over multiple iterations rather than single observations.
5. **Subset Generalisability:** Verification results for the implemented subset (Phases P0 through P8) do not imply correctness for unsupported language constructs or alternative target platforms.
