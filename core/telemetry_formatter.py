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
        
        # Per-segment steady-state analysis (WRITE only)
        self._format_per_segment_analysis(summary)
        
        # Latency table
        self._format_latency(summary)
        
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
        
        for seg_label, seg_data in sorted(per_seg.items()):
            self._format_segment(seg_label, seg_data)
        
        self._add()
    
    def _format_segment(self, seg_label: str, seg_data: Dict[str, Any]):
        """Format a single segment (one thread count)."""
        cnt = seg_data.get('sample_count', 0)
        
        # Get IOPS and bandwidth data
        iops_data = seg_data.get('iops', {})
        write_iops = iops_data.get('write_all', {})
        read_iops = iops_data.get('read_all', {}) if self.config.include_read_metrics else {}
        
        bw_data = seg_data.get('bandwidth_mbps', {})
        write_bw = bw_data.get('write_all', {})
        read_bw = bw_data.get('read_all', {}) if self.config.include_read_metrics else {}
        
        # Only show if we have meaningful write data
        if not write_iops or write_iops.get('mean', 0) < 100:
            return
        
        # Format the segment header
        if self.config.format == OutputFormat.CONSOLE:
            bold_label = color_text(seg_label, "BOLD")
            self._add(f"  {bold_label} ({cnt} samples):")
        else:
            self._add(f"**{seg_label}** ({cnt} samples):")
        
        # Format WRITE stats (always shown)
        wi_mean = write_iops.get('mean', 0)
        wi_cv = write_iops.get('cv_percent', 0)
        wb_mean = write_bw.get('mean', 0) if write_bw else 0
        rating, color = get_cv_rating(wi_cv)
        
        if self.config.format == OutputFormat.CONSOLE:
            colored_rating = color_text(rating, color)
            self._add(f"    Write: {wi_mean:>8.0f} IOPS ({wb_mean:>5.0f} MB/s) CV={wi_cv:>5.1f}% [{colored_rating}]")
        else:
            self._add(f"- **Write:** {wi_mean:,.0f} IOPS ({wb_mean:,.0f} MB/s) CV={wi_cv:.1f}% [{rating}]")
        
        # Format READ stats (only if enabled, and with warning)
        if self.config.include_read_metrics and read_iops and read_iops.get('mean', 0) > 100:
            ri_mean = read_iops.get('mean', 0)
            ri_cv = read_iops.get('cv_percent', 0)
            rb_mean = read_bw.get('mean', 0) if read_bw else 0
            rating, color = get_cv_rating(ri_cv)
            
            if self.config.format == OutputFormat.CONSOLE:
                colored_rating = color_text(rating, color)
                self._add(f"    Read:  {ri_mean:>8.0f} IOPS ({rb_mean:>5.0f} MB/s) CV={ri_cv:>5.1f}% [{colored_rating}] ⚠️ ARC")
            else:
                self._add(f"- **Read:** {ri_mean:,.0f} IOPS ({rb_mean:,.0f} MB/s) CV={ri_cv:.1f}% [{rating}] ⚠️ *ZFS ARC may inflate reads*")
        
        if self.config.format == OutputFormat.MARKDOWN:
            self._add()
    
    def _format_latency(self, summary: Dict[str, Any]):
        """Format latency table."""
        all_s = summary.get('all_samples', {})
        latency = all_s.get('latency_ms', {}) if all_s else {}
        has_latency = any(latency.values()) if latency else False
        
        if not has_latency:
            return
        
        self._subheader("Latency (ms)")
        
        if self.config.format == OutputFormat.CONSOLE:
            # Console: compact table
            self._add(f"  {'Metric':<22} {'Mean':>12} {'P99':>12} {'Std Dev':>12} {'CV%':>10} {'Rating':<15}")
            self._add(f"  {'-'*22} {'-'*12} {'-'*12} {'-'*12} {'-'*10} {'-'*15}")
            
            for metric_name, metric_key in [("Write Wait", "total_wait_write"), ("Read Wait", "total_wait_read")]:
                stats = latency.get(metric_key)
                if stats:
                    mean = stats.get('mean', 0)
                    p99 = stats.get('p99', 0)
                    std_dev = stats.get('std_dev', 0)
                    cv = stats.get('cv_percent', 0)
                    rating, color = get_cv_rating(cv)
                    colored_rating = color_text(rating, color)
                    self._add(f"  {metric_name:<22} {mean:>12.1f} {p99:>12.1f} {std_dev:>12.1f} {cv:>9.1f}% {colored_rating:<15}")
            
            self._add()
            self._add("  Legend: Mean = Average | P99 = 99th percentile | CV% = Consistency")
            self._add(f"    {color_text('<10% Excellent', 'GREEN')} | {color_text('10-20% Good', 'CYAN')} | {color_text('20-30% Variable', 'YELLOW')} | {color_text('>30% High Var', 'RED')}")
        else:
            # Markdown: proper table
            self._add("| Metric | Mean | P99 | Std Dev | CV% | Rating |")
            self._add("|--------|------|-----|---------|-----|--------|")
            
            for metric_name, metric_key in [("Write Wait", "total_wait_write"), ("Read Wait", "total_wait_read")]:
                stats = latency.get(metric_key)
                if stats:
                    mean = stats.get('mean', 0)
                    p99 = stats.get('p99', 0)
                    std_dev = stats.get('std_dev', 0)
                    cv = stats.get('cv_percent', 0)
                    rating, _ = get_cv_rating(cv)
                    self._add(f"| {metric_name} | {mean:.1f} | {p99:.1f} | {std_dev:.1f} | {cv:.1f}% | {rating} |")
            
            self._add()
            self._add("*CV% (Coefficient of Variation): <10% Excellent, 10-20% Good, 20-30% Variable, >30% High Variance*")


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
