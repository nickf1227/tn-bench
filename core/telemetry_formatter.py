"""
Unified telemetry formatter for tn-bench.

Provides a single source of truth for formatting telemetry data,
with support for both console (ANSI colors) and markdown output.
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class OutputFormat(Enum):
    """Output format for telemetry display."""
    CONSOLE = "console"    # ANSI colors, compact for terminal
    MARKDOWN = "markdown"  # Markdown tables, detailed for reports


@dataclass
class FormatConfig:
    """Configuration for formatting output."""
    format: OutputFormat
    include_nerd_stats: bool = False  # Detailed stats (markdown only)
    include_read_metrics: bool = False  # READ metrics (excluded due to ZFS ARC)


def get_cv_rating(cv: float) -> Tuple[str, str]:
    """
    Get CV% rating label and color.

    Returns:
        Tuple of (label, color) where color is for console output
    """
    if cv < 10:
        return ("Excellent", "GREEN")
    elif cv < 20:
        return ("Good", "CYAN")
    elif cv < 30:
        return ("Variable", "YELLOW")
    else:
        return ("High Variance", "RED")


def get_p99_rating(p99: float) -> Tuple[str, str]:
    """
    Get P99 latency rating label and color.
    Lower is better for latency.

    Returns:
        Tuple of (label, color) where color is for console output
    """
    if p99 < 10:
        return ("Excellent", "GREEN")
    elif p99 < 50:
        return ("Good", "CYAN")
    elif p99 < 100:
        return ("Acceptable", "YELLOW")
    else:
        return ("High", "RED")


def get_std_dev_rating(std_dev: float, metric_type: str = "iops") -> Tuple[str, str]:
    """
    Get Std Dev rating label and color based on metric type.
    Lower is better for std dev (more consistent).

    Args:
        std_dev: Standard deviation value
        metric_type: Type of metric ("iops", "bandwidth", "latency")

    Returns:
        Tuple of (label, color) where color is for console output
    """
    # Thresholds depend on the magnitude of the metric
    if metric_type == "latency":
        # Latency std dev in ms
        if std_dev < 5:
            return ("Excellent", "GREEN")
        elif std_dev < 20:
            return ("Good", "CYAN")
        elif std_dev < 50:
            return ("Variable", "YELLOW")
        else:
            return ("High Variance", "RED")
    else:
        # For IOPS and bandwidth, use relative thresholds based on typical values
        # Normalize by assuming typical mean values
        if std_dev < 100:
            return ("Excellent", "GREEN")
        elif std_dev < 500:
            return ("Good", "CYAN")
        elif std_dev < 1000:
            return ("Variable", "YELLOW")
        else:
            return ("High Variance", "RED")


def color_text(text: str, color: str) -> str:
    """Apply ANSI color to text (console only)."""
    colors = {
        "GREEN": "\033[92m",
        "CYAN": "\033[96m",
        "YELLOW": "\033[93m",
        "RED": "\033[91m",
        "BOLD": "\033[1m",
        "DIM": "\033[2m",
        "WHITE": "\033[97m",
        "BLUE": "\033[94m",
        "MAGENTA": "\033[95m",
        "RESET": "\033[0m"
    }
    return f"{colors.get(color, '')}{text}{colors['RESET']}"


class TelemetryFormatter:
    """
    Unified formatter for telemetry data.

    Generates both console output (live preview) and markdown reports
    from the same underlying data structure.
    """

    def __init__(self, config: FormatConfig):
        self.config = config
        self.lines: List[str] = []

    def _add(self, line: str = ""):
        """Add a line to output."""
        self.lines.append(line)

    def _subheader(self, text: str):
        """Add a subheader."""
        if self.config.format == OutputFormat.CONSOLE:
            # Centered with dashes
            width = 60
            padding = (width - len(text) - 2) // 2
            self._add(f"{'─' * padding} {text} {'─' * (width - padding - len(text) - 2)}")
        else:
            self._add(f"### {text}")
            self._add()

    def _bullet(self, text: str):
        """Add a bullet point."""
        if self.config.format == OutputFormat.CONSOLE:
            self._add(f"  • {text}")
        else:
            self._add(f"- {text}")

    def _note(self, text: str):
        """Add a note/explanation."""
        if self.config.format == OutputFormat.CONSOLE:
            self._add(f"  Note: {text}")
        else:
            self._add(f"> **Note:** {text}")
            self._add()

    def _format_number(self, num: float, decimals: int = 1) -> str:
        """Format a number with appropriate precision."""
        if num == 0:
            return "0"
        if num >= 10000:
            return f"{num:,.0f}"
        return f"{num:.{decimals}f}"

    def format_telemetry_summary(self, summary: Dict[str, Any], pool_name: str) -> str:
        """
        Format complete telemetry summary.

        Args:
            summary: Telemetry summary dict from calculate_zpool_iostat_summary()
            pool_name: Name of the pool being analyzed

        Returns:
            Formatted string (console or markdown based on config)
        """
        self.lines = []

        if not summary:
            self._bullet("No telemetry data available")
            return "\n".join(self.lines)

        # Header section
        self._format_header(summary, pool_name)

        # Per-segment steady-state analysis (WRITE only, includes latency)
        self._format_per_segment_analysis(summary)

        # Definitions/legend for statistical measures
        self._format_definitions()

        return "\n".join(self.lines)

    def _format_header(self, summary: Dict[str, Any], pool_name: str):
        """Format the summary header."""
        if self.config.format == OutputFormat.CONSOLE:
            width = 60
            title = f"Zpool Iostat Telemetry Summary for Pool: {pool_name}"
            padding = (width - len(title)) // 2
            self._add()
            self._add("╔" + "═" * (width - 2) + "╗")
            self._add("║" + " " * padding + title + " " * (width - padding - len(title) - 2) + "║")
            self._add("╚" + "═" * (width - 2) + "╝")
        else:
            self._add(f"## Telemetry Analysis: Pool `{pool_name}`")
            self._add()

        # Basic stats
        total = summary.get('total_samples', 0)
        ss_count = summary.get('steady_state_samples', 0)
        duration = summary.get('duration_seconds', 0)

        self._bullet(f"Total samples: {total}  |  Steady-state samples: {ss_count}")
        if duration:
            self._bullet(f"Duration: {duration:.2f} seconds")

        self._add()

    def _format_per_segment_analysis(self, summary: Dict[str, Any]):
        """Format per-segment (per-thread-count) steady-state analysis."""
        per_seg = summary.get('per_segment_steady_state', {})
        if not per_seg:
            return

        self._subheader("Per-Thread-Count Steady-State Analysis")

        if self.config.format == OutputFormat.CONSOLE:
            self._add("  WRITE telemetry only (READ excluded due to ZFS ARC cache interference)")
            self._add()
        else:
            self._note("WRITE telemetry only - READ metrics excluded due to ZFS ARC cache interference, "
                      "which can artificially inflate read performance numbers.")

        # Only show write phases, sorted numerically by thread count
        write_phases = [(label, data) for label, data in per_seg.items() if label.endswith('-write')]

        # Extract thread count and sort numerically
        def get_thread_count(item):
            label = item[0]
            # Extract number from "16T-write" format
            try:
                return int(label.split('T')[0])
            except (ValueError, IndexError):
                return 0

        for seg_label, seg_data in sorted(write_phases, key=get_thread_count):
            self._format_segment(seg_label, seg_data)

        self._add()

    def _format_segment(self, seg_label: str, seg_data: Dict[str, Any]):
        """Format a single segment (one thread count) with full stats."""
        cnt = seg_data.get('sample_count', 0)
        
        # Get IOPS, bandwidth, and latency data
        iops_data = seg_data.get('iops', {})
        write_iops = iops_data.get('write_all', {})
        
        bw_data = seg_data.get('bandwidth_mbps', {})
        write_bw = bw_data.get('write_all', {})
        
        # Get latency from the segment data if available
        latency_data = seg_data.get('latency_ms', {})
        write_latency = latency_data.get('total_wait_write', {})
        
        # Convert "16T-write" to "16 Threads" format for display
        try:
            thread_count = int(seg_label.split('T')[0])
            display_label = f"{thread_count} Threads"
        except (ValueError, IndexError):
            display_label = seg_label
        
        # Only show if we have meaningful write data (lower threshold for 1T)
        if not write_iops or write_iops.get('mean', 0) < 10:
            return
        
        # Format the segment header
        if self.config.format == OutputFormat.CONSOLE:
            bold_label = color_text(display_label, "BOLD")
            self._add(f"  {bold_label} ({cnt} samples):")
        else:
            self._add(f"**{display_label}** ({cnt} samples):")
            self._add()

        # Format IOPS stats with full detail
        self._format_metric_row("IOPS", write_iops)

        # Format Bandwidth stats with full detail
        self._format_metric_row("Bandwidth (MB/s)", write_bw)

        # Format Latency stats with full detail (WRITE only)
        # Auto-scale unit: if mean < 1ms, display in μs for NVMe-class latencies
        if write_latency:
            latency_mean = write_latency.get('mean', 0)
            if latency_mean > 0 and latency_mean < 1.0:
                # Convert positional values from ms → μs for display
                # but preserve cv_percent (it's a ratio, not a unit-dependent value)
                scaled = {}
                ratio_keys = {'cv_percent', 'count'}
                for k, v in write_latency.items():
                    if k in ratio_keys:
                        scaled[k] = v
                    elif isinstance(v, (int, float)):
                        scaled[k] = v * 1000
                    else:
                        scaled[k] = v
                self._format_metric_row("Latency (μs)", scaled, rating_stats_override=write_latency)
            else:
                self._format_metric_row("Latency (ms)", write_latency)

        if self.config.format == OutputFormat.MARKDOWN:
            self._add()

    def _format_metric_row(self, metric_name: str, stats: Dict[str, Any],
                           rating_stats_override: Dict[str, Any] = None):
        """Format a single metric row as a readable table with colorized labels and values.
        
        Args:
            metric_name: Display name for the metric (e.g. "Latency (μs)")
            stats: Stats dict with values to display (may be unit-scaled)
            rating_stats_override: If provided, use these values for rating
                calculations instead of stats. Used when display values are
                scaled (e.g. μs) but ratings should use original units (ms).
        """
        if not stats:
            return

        mean = stats.get('mean', 0)
        median = stats.get('median', 0)
        p99 = stats.get('p99', 0)
        std_dev = stats.get('std_dev', 0)
        cv = stats.get('cv_percent', 0)

        # Use override stats for ratings if provided (unit-scaling case)
        rating_src = rating_stats_override or stats
        rating_p99 = rating_src.get('p99', 0)
        rating_std = rating_src.get('std_dev', 0)
        rating_cv = rating_src.get('cv_percent', 0)

        # Get ratings for each metric (always using original-unit values)
        cv_rating, cv_color = get_cv_rating(rating_cv)
        p99_rating, p99_color = get_p99_rating(rating_p99)

        # Determine metric type for std dev rating
        metric_type = "latency" if "latency" in metric_name.lower() else "iops"
        std_rating, std_color = get_std_dev_rating(rating_std, metric_type)

        if self.config.format == OutputFormat.CONSOLE:
            # Colorized output: labels in cyan, values in white, ratings colored by rating
            dim = "DIM"
            label_color = "CYAN"      # Metric labels
            value_color = "WHITE"     # Numeric values

            # Build the table with box drawing characters
            sep = color_text("│", dim)
            row_sep = color_text("├" + "─" * 58 + "┤", dim)

            # Metric name as header
            metric_header = color_text(f"  ┌─ {metric_name} ", label_color) + color_text("─" * (56 - len(metric_name)), dim)
            self._add(metric_header)

            # Row 1: Mean, Median
            mean_str = color_text(f"{mean:,.1f}", value_color)
            median_str = color_text(f"{median:,.1f}", value_color)
            self._add(f"  {sep} {color_text('Mean:', label_color):<8} {mean_str:>12}  {sep} {color_text('Median:', label_color):<8} {median_str:>12}  {sep}")

            # Separator line
            self._add(f"  {row_sep}")

            # Row 2: P99 with rating
            p99_val_str = color_text(f"{p99:,.1f}", value_color)
            self._add(f"  {sep} {color_text('P99:', label_color):<8} {p99_val_str:>12} {color_text('[' + p99_rating + ']', p99_color):>14} {sep}")

            # Separator line
            self._add(f"  {row_sep}")

            # Row 3: Std Dev with rating
            std_str = color_text(f"{std_dev:,.1f}", value_color)
            self._add(f"  {sep} {color_text('Std Dev:', label_color):<8} {std_str:>12} {color_text('[' + std_rating + ']', std_color):>14} {sep}")

            # Separator line
            self._add(f"  {row_sep}")

            # Row 4: CV% with rating
            cv_str = color_text(f"{cv:.1f}", value_color)
            cv_rating_str = color_text(cv_rating, cv_color)
            self._add(f"  {sep} {color_text('CV%:', label_color):<8} {cv_str:>12}% {cv_rating_str:>14} {sep}")

            # Bottom border
            self._add(color_text("  └" + "─" * 58 + "┘", dim))
        else:
            # Markdown table format with ratings
            self._add(f"| Metric | Mean | Median | P99 (Rating) | Std Dev (Rating) | CV% (Rating) |")
            self._add(f"|--------|------|--------|--------------|------------------|--------------|")
            self._add(f"| {metric_name} | {mean:.1f} | {median:.1f} | {p99:.1f} ({p99_rating}) | {std_dev:.1f} ({std_rating}) | {cv:.1f}% ({cv_rating}) |")
            self._add()

    def _format_definitions(self):
        """Add definitions/legend for statistical measures with all ratings."""
        self._subheader("Legend")

        if self.config.format == OutputFormat.CONSOLE:
            self._add("  Statistical Measures:")
            self._add("    • Mean:    Average of all samples")
            self._add("    • Median:  Middle value (50th percentile), less affected by outliers")
            self._add("    • P99:     99th percentile - 99% of samples fall below this value")
            self._add("    • Std Dev: Standard deviation - measures spread/consistency")
            self._add("    • CV%:     Coefficient of Variation (std dev / mean × 100)")
            self._add()
            self._add("  CV% Rating (Consistency):")
            self._add(f"    • {color_text('Excellent', 'GREEN')}:    < 10%  (highly consistent)")
            self._add(f"    • {color_text('Good', 'CYAN')}:         10-20% (good consistency)")
            self._add(f"    • {color_text('Variable', 'YELLOW')}:     20-30% (some variability)")
            self._add(f"    • {color_text('High Variance', 'RED')}:  > 30%  (significant inconsistency)")
            self._add()
            self._add("  P99 Latency Rating (Lower is better):")
            self._add(f"    • {color_text('Excellent', 'GREEN')}:    < 10ms   (very fast)")
            self._add(f"    • {color_text('Good', 'CYAN')}:         < 50ms   (acceptable)")
            self._add(f"    • {color_text('Acceptable', 'YELLOW')}:  < 100ms  (may impact workload)")
            self._add(f"    • {color_text('High', 'RED')}:          > 100ms  (significant latency)")
            self._add()
            self._add("  Std Dev Rating (Consistency - Lower is better):")
            self._add(f"    • {color_text('Excellent', 'GREEN')}:    Low spread    (very consistent)")
            self._add(f"    • {color_text('Good', 'CYAN')}:         Moderate      (acceptable spread)")
            self._add(f"    • {color_text('Variable', 'YELLOW')}:     Noticeable    (some spread)")
            self._add(f"    • {color_text('High Variance', 'RED')}:  Wide spread   (inconsistent)")
        else:
            self._add("**Statistical Measures:**")
            self._add()
            self._add("| Measure | Definition |")
            self._add("|---------|------------|")
            self._add("| **Mean** | Average of all samples |")
            self._add("| **Median** | Middle value (50th percentile), less affected by outliers |")
            self._add("| **P99** | 99th percentile - 99% of samples fall below this value |")
            self._add("| **Std Dev** | Standard deviation - measures spread/consistency |")
            self._add("| **CV%** | Coefficient of Variation (std dev / mean × 100) |")
            self._add()
            self._add("**Rating Guides:**")
            self._add()
            self._add("| Metric | Excellent | Good | Variable/Acceptable | High/High Variance |")
            self._add("|--------|-----------|------|---------------------|-------------------|")
            self._add("| **CV%** | < 10% | 10-20% | 20-30% | > 30% |")
            self._add("| **P99 Latency** | < 10ms | < 50ms | < 100ms | > 100ms |")
            self._add("| **Std Dev** | Low | Moderate | Noticeable | Wide |")
            self._add()
            self._add("*Lower is better for P99 Latency and Std Dev. CV% is normalized.*")
            self._add()

# Convenience functions for common use cases

def format_telemetry_console(summary: Dict[str, Any], pool_name: str) -> str:
    """Format telemetry for console output (live preview)."""
    formatter = TelemetryFormatter(FormatConfig(
        format=OutputFormat.CONSOLE,
        include_nerd_stats=False,
        include_read_metrics=False
    ))
    return formatter.format_telemetry_summary(summary, pool_name)


# Alias for backward compatibility / convenience
format_telemetry_for_console = format_telemetry_console


def format_telemetry_markdown(summary: Dict[str, Any], pool_name: str, include_nerd_stats: bool = True) -> str:
    """Format telemetry for markdown report."""
    formatter = TelemetryFormatter(FormatConfig(
        format=OutputFormat.MARKDOWN,
        include_nerd_stats=include_nerd_stats,
        include_read_metrics=False
    ))
    return formatter.format_telemetry_summary(summary, pool_name)
