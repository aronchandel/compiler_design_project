"""Source text, positions and spans for the cpp2py compiler."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Pos:
    """1-based line and column, with 0-based offset into the file text."""
    line: int
    col: int
    offset: int = 0

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Half-open span [start, end) within a source file.
    ``file`` is the filename, ``start`` and ``end`` are positions.
    """
    file: str = ""
    start: Pos = field(default_factory=lambda: Pos(1, 1, 0))
    end: Pos = field(default_factory=lambda: Pos(1, 1, 0))

    def __str__(self) -> str:
        return f"{self.file}:{self.start}"


class SourceFile:
    """Represents a loaded source file and provides helpers to create spans."""

    def __init__(self, name: str = "", text: str = "", filename: str = "", content: str = "") -> None:
        self.name = filename if filename else name
        self.text = content if content else text

    @property
    def filename(self) -> str:
        return self.name

    @property
    def content(self) -> str:
        return self.text

    def _line_starts(self) -> list[int]:
        """Return list of offsets where each line begins."""
        starts = [0]
        for i, ch in enumerate(self.text):
            if ch == '\n':
                starts.append(i + 1)
        return starts

    def pos_from_offset(self, offset: int) -> Pos:
        """Convert a byte offset to a Pos (line, column, offset)."""
        prefix = self.text[:offset]
        line = prefix.count('\n') + 1
        last_nl = prefix.rfind('\n')
        col = offset - (last_nl + 1) + 1
        return Pos(line=line, col=col, offset=offset)

    def pos_at(self, line: int, col: int) -> Pos:
        """Helper to create Pos at line and col."""
        return Pos(line=line, col=col, offset=0)

    def span(self, start_off: int, end_off: int) -> SourceSpan:
        """Return a SourceSpan covering the range [start_off, end_off)."""
        start = self.pos_from_offset(start_off)
        end = self.pos_from_offset(end_off)
        return SourceSpan(file=self.name, start=start, end=end)

    def get_line(self, line_number: int) -> str:
        """Return the text of a 1-based line number (without newline)."""
        lines = self.text.split('\n')
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].rstrip('\r')
        return ''

    def line_text(self, line_number: int) -> str:
        """Alias for get_line."""
        return self.get_line(line_number)
