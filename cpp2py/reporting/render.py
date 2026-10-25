"""Rendering of Fidelity Reports to JSON and Markdown.

Conforms to ARCH §I.4 and AC7.5, AC7.6.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cpp2py.localisation import DISCLAIMER
from cpp2py.reporting.fidelity import FidelityReport


def render_fidelity_json(report: FidelityReport, out_dir: str | Path) -> Path:
    """Render fidelity report to fidelity.json."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    json_file = out_path / "fidelity.json"
    content = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    json_file.write_text(content, encoding="utf-8")
    return json_file


def render_fidelity_md(report: FidelityReport, out_dir: str | Path) -> Path:
    """Render fidelity report to fidelity.md."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    md_file = out_path / "fidelity.md"

    lines: list[str] = [
        "# Fidelity Report",
        "",
        f"**Schema Version:** `{report.schema_version}`",
        "",
        "## Run Metadata",
        "",
    ]

    meta = report.run_metadata
    if meta:
        lines.append(f"- **Tool Version:** {meta.get('tool_version', 'unknown')}")
        lines.append(f"- **Date:** {meta.get('date', 'unknown')}")
        if "source_file" in meta:
            lines.append(f"- **Source File:** `{meta['source_file']}` (SHA-256: `{meta.get('source_sha256', '')[:12]}...`)")
        if "suite" in meta:
            lines.append(f"- **Differential Suite:** `{meta['suite']}` (Seed: {meta.get('seed', 'N/A')})")
        lines.append(f"- **Reference Compiler:** {meta.get('reference_compiler', 'unknown')} ({meta.get('compiler_version', 'unknown')})")
        cfg = meta.get("config", {})
        if cfg:
            lines.append(f"- **Configuration:** `int={cfg.get('int_bits', 32)}b`, `long_long={cfg.get('long_long_bits', 64)}b`, `compat={cfg.get('compat_mode', '')}`, `overflow={cfg.get('overflow_policy', '')}`")
    else:
        lines.append("*(No metadata provided)*")
    lines.append("")

    # Translation Summary
    lines.append("## Translation Summary")
    lines.append("")
    summary = report.translation_summary
    if summary:
        lines.append(f"- **Functions Translated:** {summary.get('function_count', 0)}")
        op_counts = summary.get("operation_counts", {})
        if op_counts:
            lines.append("- **Operation Counts:** " + ", ".join(f"`{k}`: {v}" for k, v in sorted(op_counts.items())))
        passes = summary.get("passes_changed", {})
        if passes:
            lines.append("- **Passes That Modified IR:** " + ", ".join(f"`{k}`: {v} changes" for k, v in sorted(passes.items())))
        else:
            lines.append("- **Passes That Modified IR:** None")
    else:
        lines.append("*(No translation summary available)*")
    lines.append("")

    # Compatibility Helpers
    lines.append("## Compatibility Helpers")
    lines.append("")
    helpers = report.compatibility_helpers
    if helpers:
        lines.append(f"- **Helpers Inserted:** {helpers.get('inserted_count', 0)}")
        lines.append(f"- **Helpers Avoided (Classified Safe):** {helpers.get('avoided_count', 0)}")
        lines.append("")
        if helpers.get("inserted"):
            lines.append("### Inserted Helpers")
            for h in helpers["inserted"]:
                lines.append(f"- `[{h['op_id']}]` {h['location']} -> `{h['helper']}`: {h['reason']}")
            lines.append("")
        if helpers.get("avoided"):
            lines.append("### Avoided Helpers (Proven Safe Native Operators)")
            for a in helpers["avoided"]:
                lines.append(f"- `[{a['op_id']}]` {a['location']}: {a['reason']}")
            lines.append("")
    else:
        lines.append("*(No compatibility helpers section)*")
        lines.append("")

    # Reported Risks
    lines.append("## Reported-not-handled Risks")
    lines.append("")
    risks = report.reported_risks
    if risks:
        ov = risks.get("overflow_possibilities", [])
        dz = risks.get("possible_division_by_zero", [])
        nar = risks.get("lossy_narrowing", [])
        lines.append(f"- **Overflow Possibilities Under `assume_no_overflow`:** {len(ov)}")
        for r in ov:
            lines.append(f"  * `[{r['op_id']}]` {r.get('location', '')}: {r.get('reason', '')}")
        lines.append(f"- **Possible Division by Zero:** {len(dz)}")
        for r in dz:
            lines.append(f"  * `[{r['op_id']}]` {r.get('location', '')}: {r.get('reason', '')}")
        lines.append(f"- **Lossy Narrowing:** {len(nar)}")
        for r in nar:
            lines.append(f"  * `[{r['op_id']}]` {r.get('location', '')}: {r.get('reason', '')}")
    else:
        lines.append("- No unhandled risks identified.")
    lines.append("")

    # Assumptions
    lines.append("## Assumptions")
    lines.append("")
    if report.assumptions:
        for asm in report.assumptions:
            lines.append(f"- Assumed range: `{asm}`")
    else:
        lines.append("- No user-specified range assumptions active.")
    lines.append("")

    # Unsupported Constructs
    lines.append("## Unsupported Constructs")
    lines.append("")
    unsup = report.unsupported_constructs
    if unsup.get("translated") is False:
        lines.append(f"**Program Rejected:** {unsup.get('rejection_reason', 'Unsupported constructs')}")
        lines.append("")
        lines.append("Diagnostics emitted:")
        for d in unsup.get("diagnostics", []):
            lines.append(f"- `{d['code']}` at {d.get('location', '')}: {d['message']}")
    else:
        lines.append("- None (program is fully within supported subset).")
    lines.append("")

    # Potential Semantic Differences
    lines.append("## Potential Semantic Differences")
    lines.append("")
    for diff in report.potential_semantic_differences:
        lines.append(f"- {diff}")
    lines.append("")

    # Test Results (if present)
    if report.test_results:
        lines.append("## Test Results")
        lines.append("")
        tr = report.test_results
        lines.append(f"- **Total Test Executions:** {tr.get('total_executions', 0)}")
        ag = tr.get("agreement_rate", {})
        num = ag.get("numerator", 0)
        denom = ag.get("denominator", 0)
        rate = ag.get("rate")
        pct_str = f"{rate * 100:.2f}%" if rate is not None else "N/A"
        lines.append(f"- **Agreement Rate:** {num}/{denom} ({pct_str})")
        lines.append("")
        lines.append("### Outcome Counts")
        for k, v in tr.get("counts", {}).items():
            if v > 0:
                lines.append(f"- `{k}`: {v}")
        lines.append("")
        lines.append("### Excluded from Agreement Rate Denominator")
        for k, v in tr.get("excluded_counts", {}).items():
            lines.append(f"- `{k}`: {v}")
        lines.append("")

    # Mismatches & Suspects
    if report.mismatches:
        lines.append("## Mismatches and Localisation Suspects")
        lines.append("")
        lines.append(f"> **Disclaimer:** *{DISCLAIMER}*")
        lines.append("")
        for m in report.mismatches:
            lines.append(f"### Case `{m['case_id']}` ({m['outcome']})")
            lines.append(f"- **Reason:** {m.get('reason', '')}")
            loc = m.get("localisation")
            if loc:
                lines.append(f"- **Stage Verdict:** `{loc.get('stage_verdict', 'unknown')}`")
                lines.append(f"- **First Divergent Stage:** `{loc.get('first_divergent_stage', 'unknown')}`")
                lines.append(f"- **Confidence:** `{loc.get('confidence', 'heuristic')}`")
                suspects = loc.get("suspects", [])
                if suspects:
                    lines.append("- **Ranked Suspects:**")
                    for s in suspects:
                        span_info = f" ({s['span']['file']}:{s['span']['line']}:{s['span']['col']})" if "span" in s and s["span"] else ""
                        lines.append(f"  * `#{s['rank']}` `[{s['op_id']}]`{span_info} - Score: {s['score']}")
                        for ev in s.get("evidence", []):
                            lines.append(f"      - {ev}")
            lines.append("")

    # Limitations
    lines.append("## Limitations")
    lines.append("")
    lines.append(report.limitations)
    lines.append("")

    md_file.write_text("\n".join(lines), encoding="utf-8")
    return md_file
