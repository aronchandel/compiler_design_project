"""Diagnostic collection and rendering for the cpp2py compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cpp2py.source import SourceSpan, SourceFile


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single diagnostic message."""
    severity: Severity
    code: str
    message: str
    span: SourceSpan | None = None
    notes: tuple[str, ...] = ()


class DiagnosticSink:
    """Collects diagnostics during compilation."""

    def __init__(self) -> None:
        self._diagnostics: list[Diagnostic] = []
        self._error_count: int = 0
        self._max_errors: int = 20

    def error(self, code: str, message: str, span: SourceSpan | None = None,
              notes: tuple[str, ...] = ()) -> None:
        if self._error_count >= self._max_errors:
            return
        d = Diagnostic(Severity.ERROR, code, message, span, notes)
        self._diagnostics.append(d)
        self._error_count += 1

    def warning(self, code: str, message: str, span: SourceSpan | None = None,
                notes: tuple[str, ...] = ()) -> None:
        d = Diagnostic(Severity.WARNING, code, message, span, notes)
        self._diagnostics.append(d)

    def note(self, code: str, message: str, span: SourceSpan | None = None,
             notes: tuple[str, ...] = ()) -> None:
        d = Diagnostic(Severity.NOTE, code, message, span, notes)
        self._diagnostics.append(d)

    def has_errors(self) -> bool:
        return self._error_count > 0

    def error_count(self) -> int:
        return self._error_count

    def all(self) -> tuple[Diagnostic, ...]:
        return tuple(self._diagnostics)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self._diagnostics if d.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self._diagnostics if d.severity == Severity.WARNING]

    @property
    def diagnostics(self) -> list[Diagnostic]:
        return list(self._diagnostics)


def render(diag: Diagnostic, source: SourceFile | None = None) -> str:
    """Render a diagnostic as 'file:line:col: severity [CODE]: message'
    followed by the source line and a caret."""
    parts: list[str] = []
    if diag.span is not None:
        loc = f"{diag.span.file}:{diag.span.start.line}:{diag.span.start.col}"
    else:
        loc = "<unknown>"
    sev = diag.severity.value
    parts.append(f"{loc}: {sev} [{diag.code}]: {diag.message}")

    if diag.span is not None and source is not None:
        line_text = source.get_line(diag.span.start.line)
        parts.append(line_text)
        col = diag.span.start.col
        parts.append(' ' * (col - 1) + '^')

    for note in diag.notes:
        parts.append(f"  note: {note}")

    return '\n'.join(parts)
