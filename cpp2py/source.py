# source.py – source utilities per ARCHITECTURE F.1
"""Utilities for source locations, spans, and source file handling.
These classes are used throughout the compiler pipeline for diagnostics,
lexer, parser and later stages.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Pos:
    """1‑based line and column, with 0‑based offset into the file text."""
    line: int
    col: int
    offset: int

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"

@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Half‑open span [start, end) within a source file.
    `file` is the filename, `start` and `end` are positions.
    """
    file: str
    start: Pos
    end: Pos

    def __str__(self) -> str:
        return f"{self.start}-{self.end}"

@dataclass(slots=True)
class SourceFile:
    """Represents a source file and provides helper to create spans.
    `name` is the filename (or identifier), `text` is the full source text.
    """
    name: str
    text: str

    def _pos_from_offset(self, offset: int) -> Pos:
        """Convert a byte offset to a Pos (line, column, offset)."""
        prefix = self.text[:offset]
        line = prefix.count("\n") + 1
        last_nl = prefix.rfind("\n")
        col = offset - (last_nl + 1) + 1
        return Pos(line=line, col=col, offset=offset)

    def span(self, start_off: int, end_off: int) -> SourceSpan:
        """Return a SourceSpan covering the range [start_off, end_off)."""
        if start_off < 0 or end_off < start_off or end_off > len(self.text):
            raise ValueError("Invalid span offsets")
        start = self._pos_from_offset(start_off)
        end = self._pos_from_offset(end_off)
        return SourceSpan(file=self.name, start=start, end=end)


