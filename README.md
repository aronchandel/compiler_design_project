# cpp2py

A source‑to‑source translator that converts a restricted subset of C++ into readable Python.

**Status:** Phase 1 complete (see IMPLEMENTATION_PLAN.md).

## Usage

Translate a C++ source file to Python:
```bash
python -m cpp2py translate path/to/input.cpp -o path/to/output.py
```

Dump the AST without generating Python:
```bash
python -m cpp2py translate --dump-ast path/to/input.cpp
```

Check the version:
```bash
python -m cpp2py --version
```

## Running the tests

```bash
python -m pytest -q
```

The test suite contains unit and integration tests verifying the lexer, parser, semantic analyzer, code generator, CLI, and example programs.

## Project documentation

- [Architecture](ARCHITECTURE.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Agent rules](AGENTS.md)
