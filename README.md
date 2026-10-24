# cpp2py

A source‑to‑source translator that converts a restricted subset of C++ into readable Python.

**Status:** Phase 2 complete (see IMPLEMENTATION_PLAN.md).

## Usage

Translate a C++ source file to Python:
```bash
python -m cpp2py translate path/to/input.cpp -o path/to/output.py
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

Check the version:
```bash
python -m cpp2py --version
```

## Running the tests

```bash
python -m pytest -q
```

The test suite contains unit and integration tests verifying the lexer, parser, semantic analyzer, IR builder, verifier, printer, snapshots, code generator, CLI, and example programs.

## Project documentation

- [Architecture](ARCHITECTURE.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Agent rules](AGENTS.md)
