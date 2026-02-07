"""
Unified telemetry formatter for TN-Bench.

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


def color_text(text: str, color: str) -> str:
    """Apply ANSI color to text (console only)."""
    colors = {
        "GREEN": "\033[92m",
        "CYAN": "\033[96m",
        "YELLOW": "\033[93m",
        "RED": "\033[91m",
        "BOLD": "\033[1m",
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
            self._note("WRITE telemetry only — READ metrics excluded due to ZFS ARC cache interference, "
                      "which can artificially inflate read performance numbers.")
        
        # Only show write phases, sorted by thread count
        write_phases = [(label, data) for label, data in per_seg.items() if label.endswith('-write')]
        for seg_label, seg_data in sorted(write_phases):
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
        
        # Only show if we have meaningful write data
        if not write_iops or write_iops.get('mean', 0) < 100:
            return
        
        # Format the segment header
        if self.config.format == OutputFormat.CONSOLE:
            bold_label = color_text(seg_label, "BOLD")
            self._add(f"  {bold_label} ({cnt} samples):")
        else:
            self._add(f"**{seg_label}** ({cnt} samples):")
            self._add()
        
        # Format IOPS stats with full detail
        self._format_metric_row("IOPS", write_iops)
        
        # Format Bandwidth stats with full detail
        self._format_metric_row("Bandwidth (MB/s)", write_bw)
        
        # Format Latency stats with full detail (WRITE only)
        if write_latency:
            self._format_metric_row("Latency (ms)", write_latency)
        
        if self.config.format == OutputFormat.MARKDOWN:
            self._add()
    
    def _format_metric_row(self, metric_name: str, stats: Dict[str, Any]):
        """Format a single metric row with Mean, Median, P99, Std Dev, CV%."""
        if not stats:
            return
        
        mean = stats.get('mean', 0)
        median = stats.get('median', 0)
        p99 = stats.get('p99', 0)
        std_dev = stats.get('std_dev', 0)
        cv = stats.get('cv_percent', 0)
        rating, color = get_cv_rating(cv)
        
        if self.config.format == OutputFormat.CONSOLE:
            colored_rating = color_text(rating, color)
            # Compact format for console
            self._add(f"    {metric_name:<20} Mean={mean:>10.1f}  Median={median:>10.1f}  P99={p99:>10.1f}  Std={std_dev:>10.1f}  CV={cv:>6.1f}% [{colored_rating}]")
        else:
            # Markdown table format
            self._add(f"| Metric | Mean | Median | P99 | Std Dev | CV% | Rating |")
            self._add(f"|--------|------|--------|-----|---------|-----|--------|")
            self._add(f"| {metric_name} | {mean:.1f} | {median:.1f} | {p99:.1f} | {std_dev:.1f} | {cv:.1f}% | {rating} |")
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
