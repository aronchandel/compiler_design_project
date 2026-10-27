from __future__ import annotations

import csv
import io
from typing import Any

def render_comparison_markdown(metrics_data: dict[str, Any]) -> str:
    translators = metrics_data.get("translators", {})
    b0 = translators.get("B0", {})
    b1 = translators.get("B1", {})
    e = translators.get("E", {})

    static = metrics_data.get("static_unnecessary_helpers", {})
    dynamic = metrics_data.get("dynamic_unnecessary_helpers", {})
    violations = metrics_data.get("soundness_violations", [])
    suite_info = metrics_data.get("suite_info", {})

    lines: list[str] = [
        f"# Evaluation Results: Comparative Summary",
        "",
        f"**Suite:** `{suite_info.get('suite', 'benchmark')}` | **Seed:** `{suite_info.get('seed', 1)}` | **Total Test Cases (N):** `{suite_info.get('N', 0)}`",
        "",
        "| Metric | B0 (Naive) | B1 (Always-Protect) | E (Range-Guided) |",
        "|---|---|---|---|",
    ]

    def _fmt_rate(d: dict[str, Any]) -> str:
        rate = d.get("agreement_rate")
        num = d.get("numerator", 0)
        den = d.get("denominator", 0)
        if rate is not None and den > 0:
            return f"{num}/{den} ({rate * 100:.2f}%)"
        return f"{num}/{den} (N/A)"

    lines.append(f"| **Agreement Rate** | {_fmt_rate(b0)} | {_fmt_rate(b1)} | {_fmt_rate(e)} |")

    lines.append(f"| **Mismatch Count** | {b0.get('mismatch_count', 0)} | {b1.get('mismatch_count', 0)} | {e.get('mismatch_count', 0)} |")

    def _fmt_excl(d: dict[str, Any]) -> str:
        ex = d.get("excluded_counts", {})
        return str(sum(ex.values())) if isinstance(ex, dict) else str(ex)

    lines.append(f"| **Excluded Cases (UB/Error)** | {_fmt_excl(b0)} | {_fmt_excl(b1)} | {_fmt_excl(e)} |")

    lines.append(f"| **Helper Call Sites Inserted** | {b0.get('helper_sites', 0)} | {b1.get('helper_sites', 0)} | {e.get('helper_sites', 0)} |")

    ratio_str = f"{static.get('ratio_e_to_b1', 0):.4f}" if static.get("ratio_e_to_b1") is not None else "N/A"
    lines.append(f"| **Helper Ratio (E / B1)** | 0.0000 | 1.0000 | {ratio_str} |")

    prec_str = f"{static.get('precision', 0):.4f}" if static.get("precision") is not None else "N/A"
    rec_str = f"{static.get('recall', 0):.4f}" if static.get("recall") is not None else "N/A"
    unnec_cnt = static.get("unnecessary_helpers_count", 0)
    lines.append(f"| **Static Unnecessary Helpers (FP)** | 0 | {static.get('helpers_b1', 0)} | {unnec_cnt} |")
    lines.append(f"| **Static Precision vs Labels** | N/A | N/A | {prec_str} |")
    lines.append(f"| **Static Recall vs Labels** | N/A | N/A | {rec_str} |")

    dyn_ratio = dynamic.get("empirically_unnecessary_ratio")
    dyn_str = f"{dyn_ratio * 100:.2f}%" if dyn_ratio is not None else "N/A"
    lines.append(f"| **Dynamic Unnecessary Ratio** | N/A | N/A | {dyn_str} |")

    lines.append(f"| **Soundness Violations** | N/A | N/A | {len(violations)} |")

    def _fmt_size(d: dict[str, Any]) -> str:
        sz = d.get("size_proxy", {})
        return f"{sz.get('lines', 0)} lines, {sz.get('helpers', 0)} helpers"

    lines.append(f"| **Code Size Proxy** | {_fmt_size(b0)} | {_fmt_size(b1)} | {_fmt_size(e)} |")
    lines.append("")

    lines.append("## Soundness Violations")
    lines.append("")
    if not violations:
        lines.append("No soundness violations detected. Range analysis is sound across all evaluated test cases.")
    else:
        lines.append("| Case ID | Category | E Outcome | B1 Outcome | Details |")
        lines.append("|---|---|---|---|---|")
        for v in violations:
            lines.append(f"| `{v.get('case_id')}` | {v.get('category')} | `{v.get('e_outcome')}` | `{v.get('b1_outcome')}` | {v.get('details')} |")

    lines.append("")
    return "\n".join(lines)

def render_comparison_csv(metrics_data: dict[str, Any]) -> str:
    translators = metrics_data.get("translators", {})
    b0 = translators.get("B0", {})
    b1 = translators.get("B1", {})
    e = translators.get("E", {})
    static = metrics_data.get("static_unnecessary_helpers", {})
    dynamic = metrics_data.get("dynamic_unnecessary_helpers", {})
    violations = metrics_data.get("soundness_violations", [])

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["metric", "B0_naive", "B1_always", "E_range_guided"])

    def _rate(d: dict[str, Any]) -> str:
        r = d.get("agreement_rate")
        return f"{r:.4f}" if r is not None else ""

    writer.writerow(["agreement_rate", _rate(b0), _rate(b1), _rate(e)])
    writer.writerow(["numerator", b0.get("numerator", 0), b1.get("numerator", 0), e.get("numerator", 0)])
    writer.writerow(["denominator", b0.get("denominator", 0), b1.get("denominator", 0), e.get("denominator", 0)])
    writer.writerow(["mismatch_count", b0.get("mismatch_count", 0), b1.get("mismatch_count", 0), e.get("mismatch_count", 0)])
    writer.writerow(["helper_sites", b0.get("helper_sites", 0), b1.get("helper_sites", 0), e.get("helper_sites", 0)])
    writer.writerow(["helper_ratio_vs_b1", "0.0", "1.0", str(static.get("ratio_e_to_b1", ""))])
    writer.writerow(["static_unnecessary_helpers", "0", str(static.get("helpers_b1", 0)), str(static.get("unnecessary_helpers_count", 0))])
    writer.writerow(["static_precision", "", "", str(static.get("precision", ""))])
    writer.writerow(["static_recall", "", "", str(static.get("recall", ""))])
    writer.writerow(["dynamic_unnecessary_ratio", "", "", str(dynamic.get("empirically_unnecessary_ratio", ""))])
    writer.writerow(["soundness_violations", "", "", str(len(violations))])

    return out.getvalue()

def render_localisation_markdown(loc_data: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Failure Localisation Evaluation Report",
        "",
        f"**Total Seeded Faults (N):** {loc_data.get('n', 0)}",
        f"- **Top-1 Hit Rate:** {loc_data.get('top1_hits', 0)}/{loc_data.get('n', 0)} ({loc_data.get('top1_rate', 0.0) * 100:.2f}%)",
        f"- **Top-3 Hit Rate:** {loc_data.get('top3_hits', 0)}/{loc_data.get('n', 0)} ({loc_data.get('top3_rate', 0.0) * 100:.2f}%)",
        f"- **Mean Reciprocal Rank (MRR):** {loc_data.get('mrr', 0.0):.4f}",
        "",
        "## Per-Fault Localisation Breakdown",
        "",
        "| Fault ID | Name | Expected Stage | Diagnosed Stage | Expected Suspect | Rank | Reciprocal Rank | Top-1 | Top-3 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for f in loc_data.get("fault_ranks", []):
        rank_str = str(f.get("rank")) if f.get("rank") is not None else "-"
        top1_mark = "PASS" if f.get("top1") else "FAIL"
        top3_mark = "PASS" if f.get("top3") else "FAIL"
        lines.append(
            f"| `{f.get('id')}` | {f.get('name')} | `{f.get('expected_stage')}` | "
            f"`{f.get('diagnosed_stage')}` | `{f.get('expected_suspect')}` | "
            f"{rank_str} | {f.get('reciprocal_rank', 0.0):.4f} | {top1_mark} | {top3_mark} |"
        )

    lines.append("")
    return "\n".join(lines)

def render_localisation_csv(loc_data: dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "fault_id", "name", "expected_stage", "diagnosed_stage",
        "expected_suspect", "rank", "reciprocal_rank", "top1", "top3"
    ])
    for f in loc_data.get("fault_ranks", []):
        writer.writerow([
            f.get("id"),
            f.get("name"),
            f.get("expected_stage"),
            f.get("diagnosed_stage"),
            f.get("expected_suspect"),
            f.get("rank", ""),
            f.get("reciprocal_rank", 0.0),
            1 if f.get("top1") else 0,
            1 if f.get("top3") else 0,
        ])
    return out.getvalue()
