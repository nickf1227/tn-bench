"""
ARC Statistics Formatter for tn-bench.

Provides console (ANSI) and markdown output for arcstat telemetry data.
Mirrors the visual style of telemetry_formatter.py for consistency,
but focuses on READ-phase ARC cache performance metrics.
"""

from typing import Dict, Any, List, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# Rating Functions
# ═══════════════════════════════════════════════════════════════════════════

def get_arc_hit_rating(hit_pct: float) -> Tuple[str, str]:
    """Rate ARC hit percentage. Higher is better."""
    if hit_pct >= 95:
        return ("Excellent", "GREEN")
    elif hit_pct >= 85:
        return ("Good", "CYAN")
    elif hit_pct >= 70:
        return ("Variable", "YELLOW")
    else:
        return ("Poor", "RED")


def get_l2_hit_rating(hit_pct: float) -> Tuple[str, str]:
    """Rate L2ARC hit percentage. Higher is better."""
    if hit_pct >= 80:
        return ("Excellent", "GREEN")
    elif hit_pct >= 60:
        return ("Good", "CYAN")
    elif hit_pct >= 40:
        return ("Variable", "YELLOW")
    else:
        return ("Low", "RED")


def get_cv_rating(cv: float) -> Tuple[str, str]:
    """Rate coefficient of variation. Lower is better (more consistent)."""
    if cv < 10:
        return ("Excellent", "GREEN")
    elif cv < 20:
        return ("Good", "CYAN")
    elif cv < 30:
        return ("Variable", "YELLOW")
    else:
        return ("High Variance", "RED")


def get_std_dev_rating(std_dev: float) -> Tuple[str, str]:
    """Rate standard deviation for percentage-based metrics."""
    if std_dev < 2:
        return ("Excellent", "GREEN")
    elif std_dev < 5:
        return ("Good", "CYAN")
    elif std_dev < 10:
        return ("Variable", "YELLOW")
    else:
        return ("High Variance", "RED")


# ═══════════════════════════════════════════════════════════════════════════
# Color Helper
# ═══════════════════════════════════════════════════════════════════════════

def _color(text: str, color: str) -> str:
    """Apply ANSI color to text."""
    colors = {
        "GREEN": "\033[92m", "CYAN": "\033[96m", "YELLOW": "\033[93m",
        "RED": "\033[91m", "BOLD": "\033[1m", "DIM": "\033[2m",
        "WHITE": "\033[97m", "BLUE": "\033[94m", "MAGENTA": "\033[95m",
        "RESET": "\033[0m",
    }
    return f"{colors.get(color, '')}{text}{colors['RESET']}"


# ═══════════════════════════════════════════════════════════════════════════
# Console Formatter
# ═══════════════════════════════════════════════════════════════════════════

def format_arcstat_for_console(summary: Dict[str, Any], pool_name: str) -> str:
    """
    Format arcstat summary for console output (ANSI colors, box drawing).

    Args:
        summary: Dict from calculate_arcstat_summary()
        pool_name: Pool name for display

    Returns:
        Formatted string for terminal output
    """
    lines: List[str] = []

    if not summary:
        lines.append("  • No arcstat telemetry data available")
        return "\n".join(lines)

    # Header
    width = 60
    title = f"ARC Statistics Summary (READ Phase) for Pool: {pool_name}"
    if len(title) > width - 4:
        title = f"ARC Stats (READ) — {pool_name}"
    padding = max((width - len(title)) // 2, 1)
    lines.append("")
    lines.append("╔" + "═" * (width - 2) + "╗")
    lines.append("║" + " " * padding + title + " " * (width - padding - len(title) - 2) + "║")
    lines.append("╚" + "═" * (width - 2) + "╝")

    total = summary.get("total_samples", 0)
    read_count = summary.get("read_phase_samples", 0)
    duration = summary.get("duration_seconds", 0)
    has_l2arc = summary.get("has_l2arc", False)

    lines.append(f"  • Total samples: {total}  |  Read-phase samples: {read_count}")
    if duration:
        lines.append(f"  • Duration: {duration:.2f} seconds")
    if not has_l2arc:
        lines.append(f"  • L2ARC: not present (L2ARC metrics omitted)")
    lines.append("")

    # Per-segment read analysis
    per_seg = summary.get("per_segment_read", {})
    if per_seg:
        lines.append(_console_subheader("Per-Thread-Count READ ARC Analysis"))
        lines.append("  ARC cache performance during READ benchmark phases")
        lines.append("")

        # Sort by thread count
        read_phases = sorted(per_seg.items(), key=_sort_by_thread_count)

        for seg_label, seg_data in read_phases:
            seg_lines = _format_console_segment(seg_label, seg_data, has_l2arc=has_l2arc)
            lines.extend(seg_lines)

        lines.append("")

    # Legend
    lines.extend(_format_console_legend(has_l2arc=has_l2arc))

    return "\n".join(lines)


def _console_subheader(text: str) -> str:
    """Format a console subheader with dashes."""
    width = 60
    padding = (width - len(text) - 2) // 2
    return f"{'─' * padding} {text} {'─' * (width - padding - len(text) - 2)}"


def _sort_by_thread_count(item):
    """Sort key to extract thread count from segment label."""
    label = item[0]
    try:
        return int(label.split("T")[0])
    except (ValueError, IndexError):
        return 0


def _format_console_segment(seg_label: str, seg_data: Dict[str, Any], has_l2arc: bool = False) -> List[str]:
    """Format a single READ segment for console output."""
    lines: List[str] = []
    cnt = seg_data.get("sample_count", 0)

    # Convert label: "16T-read" → "16 Threads"
    try:
        thread_count = int(seg_label.split("T")[0])
        display_label = f"{thread_count} Threads"
    except (ValueError, IndexError):
        display_label = seg_label

    bold_label = _color(display_label, "BOLD")
    lines.append(f"  {bold_label} ({cnt} samples):")

    # ARC Hit Rate
    arc_hit = seg_data.get("arc_hit_pct", {})
    if arc_hit:
        lines.extend(_format_console_metric_pct("ARC Hit %", arc_hit, get_arc_hit_rating))

    # ARC Size
    arc_size = seg_data.get("arc_size_gib", {})
    if arc_size:
        lines.extend(_format_console_metric_val("ARC Size (GiB)", arc_size))

    # L2ARC — only if pool actually has cache devices
    if has_l2arc:
        l2_hit = seg_data.get("l2_hit_pct", {})
        if l2_hit and l2_hit.get("mean", 0) > 0:
            lines.extend(_format_console_metric_pct("L2ARC Hit %", l2_hit, get_l2_hit_rating))

        l2_bytes = seg_data.get("l2_bytes_per_sec_mbs", {})
        if l2_bytes and l2_bytes.get("mean", 0) > 0:
            lines.extend(_format_console_metric_val("L2ARC Read (MB/s)", l2_bytes))

    return lines


def _format_console_metric_pct(
    metric_name: str, stats: Dict[str, Any], rating_fn
) -> List[str]:
    """Format a percentage-based metric with box drawing (matching iostat style)."""
    lines: List[str] = []
    mean = stats.get("mean", 0)
    median = stats.get("median", 0)
    p99 = stats.get("p99", 0)
    std_dev = stats.get("std_dev", 0)
    cv = stats.get("cv_percent", 0)

    # Use the rating function for the mean value
    mean_rating, mean_color = rating_fn(mean)
    cv_rating, cv_color = get_cv_rating(cv)
    std_rating, std_color = get_std_dev_rating(std_dev)

    dim = "DIM"
    lbl = "CYAN"
    val = "WHITE"
    sep = _color("│", dim)
    row_sep = _color("├" + "─" * 58 + "┤", dim)

    # Metric header
    lines.append(_color(f"  ┌─ {metric_name} ", lbl) + _color("─" * (56 - len(metric_name)), dim))

    # Row 1: Mean with rating, Median
    mean_str = _color(f"{mean:.1f}%", val)
    median_str = _color(f"{median:.1f}%", val)
    lines.append(f"  {sep} {_color('Mean:', lbl):<8} {mean_str:>12} {_color('[' + mean_rating + ']', mean_color):>14} {sep}")
    lines.append(f"  {row_sep}")

    # Row 2: Median
    lines.append(f"  {sep} {_color('Median:', lbl):<8} {median_str:>12}  {sep}")
    lines.append(f"  {row_sep}")

    # Row 3: Std Dev
    std_str = _color(f"{std_dev:.1f}", val)
    lines.append(f"  {sep} {_color('Std Dev:', lbl):<8} {std_str:>12} {_color('[' + std_rating + ']', std_color):>14} {sep}")
    lines.append(f"  {row_sep}")

    # Row 4: CV%
    cv_str = _color(f"{cv:.1f}", val)
    lines.append(f"  {sep} {_color('CV%:', lbl):<8} {cv_str:>12}% {_color(cv_rating, cv_color):>14} {sep}")

    # Bottom border
    lines.append(_color("  └" + "─" * 58 + "┘", dim))

    return lines


def _format_console_metric_val(
    metric_name: str, stats: Dict[str, Any]
) -> List[str]:
    """Format a value-based metric (non-percentage) with box drawing."""
    lines: List[str] = []
    mean = stats.get("mean", 0)
    median = stats.get("median", 0)
    p99 = stats.get("p99", 0)
    std_dev = stats.get("std_dev", 0)
    cv = stats.get("cv_percent", 0)

    cv_rating, cv_color = get_cv_rating(cv)

    dim = "DIM"
    lbl = "CYAN"
    val = "WHITE"
    sep = _color("│", dim)
    row_sep = _color("├" + "─" * 58 + "┤", dim)

    lines.append(_color(f"  ┌─ {metric_name} ", lbl) + _color("─" * (56 - len(metric_name)), dim))

    mean_str = _color(f"{mean:,.2f}", val)
    median_str = _color(f"{median:,.2f}", val)
    lines.append(f"  {sep} {_color('Mean:', lbl):<8} {mean_str:>12}  {sep} {_color('Median:', lbl):<8} {median_str:>12}  {sep}")
    lines.append(f"  {row_sep}")

    p99_str = _color(f"{p99:,.2f}", val)
    lines.append(f"  {sep} {_color('P99:', lbl):<8} {p99_str:>12}               {sep}")
    lines.append(f"  {row_sep}")

    std_str = _color(f"{std_dev:,.2f}", val)
    lines.append(f"  {sep} {_color('Std Dev:', lbl):<8} {std_str:>12}               {sep}")
    lines.append(f"  {row_sep}")

    cv_str = _color(f"{cv:.1f}", val)
    lines.append(f"  {sep} {_color('CV%:', lbl):<8} {cv_str:>12}% {_color(cv_rating, cv_color):>14} {sep}")

    lines.append(_color("  └" + "─" * 58 + "┘", dim))

    return lines


def _format_console_legend(has_l2arc: bool = False) -> List[str]:
    """ARC-specific legend for console output."""
    lines: List[str] = []
    lines.append(_console_subheader("ARC Legend"))
    lines.append("  ARC Metrics:")
    lines.append("    • ARC Hit %:       Percentage of reads served from ARC (higher = better)")
    lines.append("    • ARC Size (GiB):  Total ARC memory usage")
    if has_l2arc:
        lines.append("    • L2ARC Hit %:     Percentage of L2ARC reads that were hits")
        lines.append("    • L2ARC Read:      Data read from L2ARC device (MB/s)")
    lines.append("")
    lines.append("  ARC Hit % Rating:")
    lines.append(f"    • {_color('Excellent', 'GREEN')}:    ≥ 95%  (nearly all reads from cache)")
    lines.append(f"    • {_color('Good', 'CYAN')}:         85-95% (majority cached)")
    lines.append(f"    • {_color('Variable', 'YELLOW')}:     70-85% (moderate caching)")
    lines.append(f"    • {_color('Poor', 'RED')}:          < 70%  (frequent cache misses)")
    if has_l2arc:
        lines.append("")
        lines.append("  L2ARC Hit % Rating:")
        lines.append(f"    • {_color('Excellent', 'GREEN')}:    ≥ 80%")
        lines.append(f"    • {_color('Good', 'CYAN')}:         60-80%")
        lines.append(f"    • {_color('Variable', 'YELLOW')}:     40-60%")
        lines.append(f"    • {_color('Low', 'RED')}:           < 40%")
    lines.append("")
    return lines


# ═══════════════════════════════════════════════════════════════════════════
# Markdown Formatter
# ═══════════════════════════════════════════════════════════════════════════

def format_arcstat_for_markdown(summary: Dict[str, Any], pool_name: str) -> str:
    """
    Format arcstat summary for markdown report output.

    Args:
        summary: Dict from calculate_arcstat_summary()
        pool_name: Pool name for display

    Returns:
        Formatted markdown string
    """
    lines: List[str] = []

    if not summary:
        lines.append("- No arcstat telemetry data available")
        return "\n".join(lines)

    lines.append(f"## ARC Cache Analysis (READ Phase): Pool `{pool_name}`")
    lines.append("")

    total = summary.get("total_samples", 0)
    read_count = summary.get("read_phase_samples", 0)
    duration = summary.get("duration_seconds", 0)

    has_l2arc = summary.get("has_l2arc", False)

    lines.append(f"- **Total samples:** {total}  |  **Read-phase samples:** {read_count}")
    if duration:
        lines.append(f"- **Duration:** {duration:.2f} seconds")
    if not has_l2arc:
        lines.append(f"- **L2ARC:** not present (L2ARC metrics omitted)")
    lines.append("")

    # Per-segment
    per_seg = summary.get("per_segment_read", {})
    if per_seg:
        lines.append("### Per-Thread-Count READ ARC Performance")
        lines.append("")
        lines.append("> **Note:** ARC statistics during READ phases show how effectively "
                     "ZFS caches are serving read requests. Higher hit rates indicate "
                     "better cache utilization.")
        lines.append("")

        read_phases = sorted(per_seg.items(), key=_sort_by_thread_count)

        for seg_label, seg_data in read_phases:
            seg_lines = _format_markdown_segment(seg_label, seg_data, has_l2arc=has_l2arc)
            lines.extend(seg_lines)

    # Legend
    lines.extend(_format_markdown_legend(has_l2arc=has_l2arc))

    return "\n".join(lines)


def _format_markdown_segment(seg_label: str, seg_data: Dict[str, Any], has_l2arc: bool = False) -> List[str]:
    """Format a single READ segment for markdown output."""
    lines: List[str] = []
    cnt = seg_data.get("sample_count", 0)

    try:
        thread_count = int(seg_label.split("T")[0])
        display_label = f"{thread_count} Threads"
    except (ValueError, IndexError):
        display_label = seg_label

    lines.append(f"**{display_label}** ({cnt} samples):")
    lines.append("")

    # ARC Hit %
    arc_hit = seg_data.get("arc_hit_pct", {})
    if arc_hit:
        lines.extend(_format_markdown_metric_row("ARC Hit %", arc_hit, get_arc_hit_rating))

    # ARC Size
    arc_size = seg_data.get("arc_size_gib", {})
    if arc_size:
        lines.extend(_format_markdown_metric_row("ARC Size (GiB)", arc_size))

    # L2ARC — only if pool has cache devices
    if has_l2arc:
        l2_hit = seg_data.get("l2_hit_pct", {})
        if l2_hit and l2_hit.get("mean", 0) > 0:
            lines.extend(_format_markdown_metric_row("L2ARC Hit %", l2_hit, get_l2_hit_rating))

        l2_bytes = seg_data.get("l2_bytes_per_sec_mbs", {})
        if l2_bytes and l2_bytes.get("mean", 0) > 0:
            lines.extend(_format_markdown_metric_row("L2ARC Read (MB/s)", l2_bytes))

    return lines


def _format_markdown_metric_row(
    metric_name: str, stats: Dict[str, Any], rating_fn=None
) -> List[str]:
    """Format a metric as a markdown table row."""
    lines: List[str] = []
    mean = stats.get("mean", 0)
    median = stats.get("median", 0)
    p99 = stats.get("p99", 0)
    std_dev = stats.get("std_dev", 0)
    cv = stats.get("cv_percent", 0)

    cv_rating, _ = get_cv_rating(cv)

    # Build rating string for the mean value if a rating function was provided
    mean_rating_str = ""
    if rating_fn:
        rating_label, _ = rating_fn(mean)
        mean_rating_str = f" ({rating_label})"

    lines.append(f"| Metric | Mean | Median | P99 | Std Dev | CV% (Rating) |")
    lines.append(f"|--------|------|--------|-----|---------|--------------|")
    lines.append(
        f"| {metric_name} "
        f"| {mean:.1f}{mean_rating_str} "
        f"| {median:.1f} "
        f"| {p99:.1f} "
        f"| {std_dev:.1f} "
        f"| {cv:.1f}% ({cv_rating}) |"
    )
    lines.append("")

    return lines


def _format_markdown_legend(has_l2arc: bool = False) -> List[str]:
    """ARC-specific legend for markdown."""
    lines: List[str] = []
    lines.append("### ARC Metrics Legend")
    lines.append("")
    lines.append("| Metric | Description |")
    lines.append("|--------|------------|")
    lines.append("| **ARC Hit %** | Percentage of reads served from ARC memory cache (higher = better) |")
    lines.append("| **ARC Size** | Total ARC memory usage in GiB |")
    if has_l2arc:
        lines.append("| **L2ARC Hit %** | Percentage of L2ARC lookups that were hits |")
        lines.append("| **L2ARC Read** | Data read throughput from L2ARC device in MB/s |")
    lines.append("")
    lines.append("**ARC Hit % Rating:**")
    lines.append("")
    lines.append("| Rating | Threshold | Meaning |")
    lines.append("|--------|-----------|---------|")
    lines.append("| Excellent | ≥ 95% | Nearly all reads served from cache |")
    lines.append("| Good | 85-95% | Majority of reads cached |")
    lines.append("| Variable | 70-85% | Moderate cache utilization |")
    lines.append("| Poor | < 70% | Frequent cache misses — consider tuning |")
    if has_l2arc:
        lines.append("")
        lines.append("**L2ARC Hit % Rating:**")
        lines.append("")
        lines.append("| Rating | Threshold | Meaning |")
        lines.append("|--------|-----------|---------|")
        lines.append("| Excellent | ≥ 80% | High L2ARC cache effectiveness |")
        lines.append("| Good | 60-80% | Moderate L2ARC utilization |")
        lines.append("| Variable | 40-60% | L2ARC partially effective |")
        lines.append("| Low | < 40% | L2ARC not contributing significantly |")
    lines.append("")
    return lines
