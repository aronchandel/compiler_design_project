from __future__ import annotations

import builtins
import keyword

_RESERVED: frozenset[str] = frozenset(
    set(keyword.kwlist)
    | set(dir(builtins))
    | {'sys', 'main', '_tokens'}
)

class NameMangler:

    def __init__(self) -> None:
        self._mapping: dict[str, str] = {}
        self._used: set[str] = set()

    def mangle(self, name: str) -> str:
        if name in self._mapping:
            return self._mapping[name]

        candidate = name

        if name.startswith('_cpp') or name in _RESERVED:
            candidate = name + '_'

        while candidate in self._used:
            candidate += '_'

        self._mapping[name] = candidate
        self._used.add(candidate)
        return candidate

    def get(self, name: str) -> str:
        return self._mapping[name]

    def has(self, name: str) -> bool:
        return name in self._mapping
