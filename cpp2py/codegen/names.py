"""Python-safe name mangling for the cpp2py code generator."""

from __future__ import annotations

import builtins
import keyword


# Names that must be mangled: Python keywords, builtins, and our own generated names
_RESERVED: frozenset[str] = frozenset(
    set(keyword.kwlist)
    | set(dir(builtins))
    | {'sys', 'main', '_tokens'}
)


class NameMangler:
    """Mangle C++ identifiers to avoid Python name collisions."""

    def __init__(self) -> None:
        self._mapping: dict[str, str] = {}
        self._used: set[str] = set()

    def mangle(self, name: str) -> str:
        """Return the Python-safe name for a C++ identifier."""
        if name in self._mapping:
            return self._mapping[name]

        candidate = name

        # If name starts with _cpp, or is reserved, append _
        if name.startswith('_cpp') or name in _RESERVED:
            candidate = name + '_'

        # Resolve collisions with other already-used names
        while candidate in self._used:
            candidate += '_'

        self._mapping[name] = candidate
        self._used.add(candidate)
        return candidate

    def get(self, name: str) -> str:
        """Get the already-mangled name (raises KeyError if not yet mangled)."""
        return self._mapping[name]

    def has(self, name: str) -> bool:
        """Check if a name has been mangled."""
        return name in self._mapping
