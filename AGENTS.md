# AGENTS.md — Persistent rules for coding agents working on `cpp2py`

These rules apply to every task in this repository. Phase-specific instructions live in `IMPLEMENTATION_PLAN.md`; the design lives in `ARCHITECTURE.md`. If this file, the plan and the architecture disagree, stop and ask.

## Project in one paragraph

`cpp2py` translates a restricted subset of C++ into readable Python. Range analysis on a custom IR decides where compatibility helpers (for C++ integer semantics) are needed. It is built **one phase at a time** (P0–P8). Python ≥ 3.10, standard library only at runtime, `pytest` for tests.

## Rules

1. **Read first.** Before modifying code, read `ARCHITECTURE.md` and the relevant phase section of `IMPLEMENTATION_PLAN.md`. Inspect the existing repository; do not assume a feature exists because a document mentions it.
2. **One phase at a time.** Implement only the explicitly requested phase.
3. **No look-ahead.** Do not start later phases, and do not create stubs, placeholders or empty modules for them.
4. **Preserve working code.** No unrelated refactoring. Do not replace substantive existing work with stubs or mocks. Removals happen only where the plan explicitly sanctions them (the only one is the Phase 1 bootstrap generator, removed in Phase 3).
5. **Do not widen the C++ subset.** Anything outside the supported subset (ARCH §A.3–A.4) must be rejected with a diagnostic (`E4xxx`), never translated approximately.
6. **Respect module boundaries.** Follow the layering of ARCH §C.1 and the interfaces of ARCH §F. The IR carries C++ semantics; compatibility is decided in the `CompatPlan` and applied only by the code generator. Passes mutate IR only through `IRRewriter`.
7. **Tests with every feature.** Write unit and integration tests alongside the code. Tests assert diagnostic codes, not message wording.
8. **Run before declaring.** Run the tests and the phase's commands, read the real output, fix failures, and only then report.
9. **Never fabricate.** Do not invent test results, command output, benchmark numbers or completed functionality. If something could not be run (for example no `g++`), say so and mark it `NOT VERIFIED`.
10. **Document deviations.** If a justified deviation from the architecture is needed, stop, explain it, and record it in the Deviations log in `IMPLEMENTATION_PLAN.md` with its consequences. Do not deviate silently.
11. **Status honesty.** Update checklists and the status table in `IMPLEMENTATION_PLAN.md` only for work you verified in this session. Use `VERIFIED` only when every acceptance criterion was run and checked.
12. **Safety of output.** Translator output must never silently misrepresent C++ semantics: warnings (`W6xxx`) must be emitted, and no output file is written when there are errors.
13. **Dependencies.** No new runtime dependencies. Development dependencies only with explicit approval.
14. **Determinism.** Generated artifacts (IR text, snapshots, plans, reports' deterministic parts) must be byte-identical across runs: no timestamps, no unordered iteration, seeded randomness only.
15. **Final report format.** End each task with: files created/changed, tests added, commands run with their real results, acceptance criteria as PASS/FAIL/NOT VERIFIED, open issues.

## Commands (from repo root)

```text
python -m pytest -q                      # all tests
python -m pytest -q -m requires_cxx      # tests needing g++ (Phase 6+)
python -m cpp2py translate FILE.cpp -o out/FILE.py
```

## Conventions

Package `cpp2py/`; examples in `examples/<phase>/` (`name.cpp`, optional `name.in`, `name.expected`); generated files in git-ignored `out/`; error codes per ARCH §F.1; op IDs `op_<n>` are never reused.
