# cpp2py

A source‑to‑source translator that converts a restricted subset of C++ into readable Python.

**Status:** Phase 7 complete (failure localisation, backward def-use dynamic trace slicing, heuristic ranking, and fidelity reports; see IMPLEMENTATION_PLAN.md).

## Usage

Translate a C++ source file to Python:
```bash
python -m cpp2py translate path/to/input.cpp -o path/to/output.py
```

Compatibility modes and overflow policies:
```bash
python -m cpp2py translate path/to/input.cpp --compat range_guided --overflow assume_no_overflow -o path/to/output.py
```

Dump the AST without generating Python:
```bash
python -m cpp2py translate --dump-ast path/to/input.cpp
```

Dump the IR without generating Python:
```bash
python -m cpp2py translate --dump-ir path/to/input.cpp
```

Save compilation snapshots to a directory:
```bash
python -m cpp2py translate path/to/input.cpp --snapshots path/to/snapshots/ -o path/to/output.py
```

Generate a translation fidelity report (JSON and Markdown):
```bash
python -m cpp2py translate path/to/input.cpp --fidelity-report out/fidelity_dir -o path/to/output.py
```

### Differential Testing

Run differential testing against the reference C++ compiler (`g++`):
```bash
python -m cpp2py difftest --suite curated --compat range_guided --out out/dt_rg
python -m cpp2py difftest --suite curated --compat naive --out out/dt_naive
python -m cpp2py difftest --suite generated --seed 1 --count 200 --compat range_guided --out out/dt_gen
```

Generate differential testing fidelity reports:
```bash
python -m cpp2py difftest --suite curated --compat range_guided --fidelity-report out/fid_dt --out out/dt
```

### Failure Localisation

Localise the root-cause stage and rank suspect operations for a differential test failure:
```bash
python -m cpp2py localise --case out/dt_naive/failures/case_01_div_neg_pos --top 5
```

Check the version:
```bash
python -m cpp2py --version
```

## Running the tests

Run all tests:
```bash
python -m pytest -q
```

Run compiler-dependent tests (differential tests against `g++` and localisation faults):
```bash
python -m pytest -q -m requires_cxx
```

The test suite contains unit and integration tests verifying the lexer, parser, semantic analyzer, IR builder, verifier, printer, transforms, range analysis, compatibility plan, code generator, differential testing runners, comparator, corpus, automated generator, regression store, IR serialization, reference IR interpreter, dynamic slicing, suspect ranking, fault localisation, and fidelity reports.

## Project documentation

- [Architecture](ARCHITECTURE.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Agent rules](AGENTS.md)
