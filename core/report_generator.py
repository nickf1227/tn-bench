"""
TN-Bench Markdown Report Generator
Generates human-readable markdown reports from analytics JSON.
Part of TN-Bench 2.1
"""

import json
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional


def generate_markdown_report(analytics_data: Dict[str, Any], source_file: str) -> str:
    """Generate a markdown report from analytics data."""
    lines = []

    # Header
    lines.append("# TN-Bench Analytics Report")
    lines.append("")
    lines.append(f"**Source:** `{source_file}`")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Metrics Glossary (if telemetry data present)
    if analytics_data.get("telemetry_analyses"):
        lines.extend(_format_metrics_glossary())

    # Pool Analyses (scaling)
    for pool in analytics_data.get("pool_analyses", []):
        lines.extend(_format_pool_section(pool))

    # Disk Comparison
    lines.extend(_format_disk_section(analytics_data.get("disk_comparison", {})))

    # Telemetry Analyses
    for ta in analytics_data.get("telemetry_analyses", []):
        lines.extend(_format_telemetry_section(ta))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# Metrics Glossary
# ══════════════════════════════════════════════════════════════

def _format_metrics_glossary() -> list:
    """Format the metrics glossary section."""
    lines = []
    
    lines.append("## Metrics Glossary")
    lines.append("")
    lines.append("This report analyzes zpool iostat telemetry collected during the benchmark. "
                 "Below are definitions for the metrics and statistics presented.")
    lines.append("")
    
    # IOPS Section
    lines.append("### IOPS (Input/Output Operations Per Second)")
    lines.append("")
    lines.append("- **Write IOPS**: Number of write operations completed per second. "
                 "Higher is better for write-heavy workloads.")
    lines.append("- **Read IOPS**: Number of read operations completed per second. "
                 "Higher is better for read-heavy workloads.")
    lines.append("- **Total IOPS**: Combined read + write operations per second.")
    lines.append("")
    
    # Bandwidth Section
    lines.append("### Bandwidth (Throughput)")
    lines.append("")
    lines.append("- **Write Bandwidth**: Data write speed in MB/s (megabytes per second). "
                 "This includes ZFS overhead (parity for RAIDZ, mirroring, etc.) and may not "
                 "match the raw benchmark speed.")
    lines.append("- **Read Bandwidth**: Data read speed in MB/s. Higher is better.")
    lines.append("- **Note**: Bandwidth from zpool iostat reflects actual ZFS pool activity, "
                 "including metadata, compression, and redundancy overhead.")
    lines.append("")
    
    # Latency Section
    lines.append("### Latency (Wait Times)")
    lines.append("")
    lines.append("- **Total Wait**: Total time from I/O request submission to completion (ms). "
                 "Lower is better. Includes queue time + disk time.")
    lines.append("- **Disk Wait**: Time spent actively reading/writing to disk (ms). "
                 "Lower is better. Excludes queue time.")
    lines.append("- **Async Queue Wait**: Time spent in ZFS async write queue (ms). "
                 "Non-blocking writes may show 0 here.")
    lines.append("- **Sync Queue Wait**: Time spent in ZFS sync write queue (ms). "
                 "Important for synchronous workloads (databases, NFS).")
    lines.append("")
    
    # Statistics Section
    lines.append("### Statistical Measures")
    lines.append("")
    lines.append("- **Mean (Average)**: The arithmetic average of all samples. "
                 "Calculated by adding all values and dividing by the count. "
                 "Represents typical performance but can be skewed by outliers.")
    lines.append("")
    lines.append("- **Median**: The middle value when all samples are sorted in order. "
                 "Half the samples are above this value, half are below. "
                 "Less affected by extreme outliers than the mean.")
    lines.append("")
    lines.append("- **P99 (99th Percentile)**: The value below which 99% of all samples fall. "
                 "Only 1% of samples exceed this value. "
                 "Useful for identifying worst-case performance ('tail latency').")
    lines.append("")
    lines.append("- **Std Dev (Standard Deviation)**: Measures how spread out values are from the mean. "
                 "Higher = more variable performance. Lower = more consistent. "
                 "Calculated as the square root of the variance.")
    lines.append("")
    lines.append("- **CV% (Coefficient of Variation)**: A normalized measure of consistency calculated as: "
                 "**Std Dev ÷ Mean × 100**. This allows comparison across different scales.")
    lines.append("")
    lines.append("  **Consistency Guidelines:**")
    lines.append("  - **< 10%**: Very consistent (excellent)")
    lines.append("  - **10-20%**: Moderately consistent (good)")
    lines.append("  - **20-30%**: Variable (acceptable)")
    lines.append("  - **> 30%**: Highly variable (may indicate issues)")
    lines.append("")
    
    # Phases Section
    lines.append("### Activity Phases")
    lines.append("")
    lines.append("The benchmark timeline is segmented into phases based on I/O activity:")
    lines.append("")
    lines.append("- **IDLE**: No I/O activity detected. Occurs between test iterations "
                 "or during setup/teardown.")
    lines.append("- **WRITE**: Active write operations. Benchmark is writing test data.")
    lines.append("- **READ**: Active read operations. Benchmark is reading/verifying data.")
    lines.append("- **MIXED**: Both read and write operations active simultaneously. "
                 "Typically seen during phase transitions.")
    lines.append("")
    lines.append("Statistics are reported separately for 'all samples' and 'active only' "
                 "(excluding IDLE periods) to show true performance during I/O.")
    lines.append("")
    
    # Anomalies Section
    lines.append("### Anomaly Detection")
    lines.append("")
    lines.append("Statistical outliers detected using **z-score analysis**. "
                 "The z-score measures how many standard deviations a value is from the mean.")
    lines.append("")
    lines.append("**Z-Score Interpretation:**")
    lines.append("- **|z| < 2**: Normal variation (within 95% of data)")
    lines.append("- **|z| > 3**: Statistical outlier (anomaly) — only 0.3% of normal data falls here")
    lines.append("- **Positive z**: Value is above average")
    lines.append("- **Negative z**: Value is below average")
    lines.append("")
    lines.append("**Anomaly Types:**")
    lines.append("- **Spike**: Sudden increase in IOPS/bandwidth or latency")
    lines.append("- **Drop**: Sudden decrease in IOPS/bandwidth")
    lines.append("")
    lines.append("Most anomalies occur at phase transitions (ramp-up/ramp-down) and are normal. "
                 "Sustained anomalies during steady-state may indicate performance issues.")
    lines.append("")
    
    # I/O Size Section
    lines.append("### I/O Size Analysis")
    lines.append("")
    lines.append("- **KB/op**: Average kilobytes per operation. "
                 "Indicates sequential (large) vs random (small) I/O patterns.")
    lines.append("- TN-Bench uses large sequential I/O (~900KB-1MB per operation).")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return lines

# ══════════════════════════════════════════════════════════════
# Scaling Sections (unchanged)
# ══════════════════════════════════════════════════════════════

def _format_pool_section(pool: Dict[str, Any]) -> list:
    """Format a single pool section."""
    lines = []
    name = pool.get("name", "unknown")

    lines.append(f"## Pool: {name}")
    lines.append("")

    # Write Scaling
    write = pool.get("write_scaling", {})
    if write:
        lines.append("### Write Scaling")
        lines.append("")
        lines.append(f"- **Peak Performance:** {write.get('peak_speed_mbps', 0)} MB/s at {write.get('optimal_threads', 0)} threads")
        lines.append(f"- **Thread Efficiency:** {write.get('thread_efficiency', 0)} MB/s per thread")
        lines.append(f"- **Scaling Transitions:** {write.get('positive_transitions', 0)} positive, {write.get('negative_transitions', 0)} negative")
        lines.append("")

        # Progression table
        lines.append("| Threads | Speed (MB/s) | vs Single-Thread |")
        lines.append("|---------|-------------|------------------|")
        for step in write.get("progression", []):
            lines.append(f"| {step['threads']} | {step['speed_mbps']} | {step['vs_single_thread']}x |")
        lines.append("")

        # Delta table
        deltas = write.get("deltas", [])
        if deltas:
            lines.append("**Thread Count Transitions:**")
            lines.append("")
            lines.append("| From | To | Δ Speed | % Change |")
            lines.append("|------|----|---------|----------|")
            for d in deltas:
                sign = "+" if d['delta_mbps'] > 0 else ""
                lines.append(f"| {d['from_threads']} | {d['to_threads']} | {sign}{d['delta_mbps']} | {sign}{d['pct_change']}% |")
            lines.append("")

    # Read Scaling
    read = pool.get("read_scaling", {})
    if read:
        lines.append("### Read Scaling")
        lines.append("")
        lines.append(f"- **Peak Performance:** {read.get('peak_speed_mbps', 0)} MB/s at {read.get('optimal_threads', 0)} threads")
        lines.append(f"- **Thread Efficiency:** {read.get('thread_efficiency', 0)} MB/s per thread")
        lines.append(f"- **Scaling Transitions:** {read.get('positive_transitions', 0)} positive, {read.get('negative_transitions', 0)} negative")
        lines.append("")

        # Progression table
        lines.append("| Threads | Speed (MB/s) | vs Single-Thread |")
        lines.append("|---------|-------------|------------------|")
        for step in read.get("progression", []):
            lines.append(f"| {step['threads']} | {step['speed_mbps']} | {step['vs_single_thread']}x |")
        lines.append("")

        # Delta table
        deltas = read.get("deltas", [])
        if deltas:
            lines.append("**Thread Count Transitions:**")
            lines.append("")
            lines.append("| From | To | Δ Speed | % Change |")
            lines.append("|------|----|---------|----------|")
            for d in deltas:
                sign = "+" if d['delta_mbps'] > 0 else ""
                lines.append(f"| {d['from_threads']} | {d['to_threads']} | {sign}{d['delta_mbps']} | {sign}{d['pct_change']}% |")
            lines.append("")

    # Observations
    observations = pool.get("observations", [])
    if observations:
        lines.append("### Observations")
        lines.append("")
        for obs in observations:
            lines.append(f"- {obs.get('description', '')}")
        lines.append("")

    return lines


def _format_disk_section(disk_comparison: Dict[str, Any]) -> list:
    """Format the disk comparison section."""
    lines = []

    if not disk_comparison:
        return lines

    lines.append("## Disk Comparison")
    lines.append("")
    lines.append("Per-disk performance relative to pool average.")
    lines.append("")

    for pool_name, stats in disk_comparison.items():
        lines.append(f"### Pool: {pool_name}")
        lines.append("")
        lines.append(f"- **Pool Average:** {stats.get('pool_average_mbps', 0)} MB/s")
        lines.append(f"- **Variance:** {stats.get('variance_pct', 0)}%")
        lines.append("")

        lines.append("| Disk | Model | Speed (MB/s) | % of Pool Avg | % of Pool Max |")
        lines.append("|------|-------|-------------|---------------|---------------|")

        for disk in stats.get("disks", []):
            lines.append(
                f"| {disk.get('disk', 'unknown')} | "
                f"{disk.get('model', 'unknown')[:25]} | "
                f"{disk.get('speed_mbps', 0)} | "
                f"{disk.get('pct_of_pool_avg', 0)}% | "
                f"{disk.get('pct_of_pool_max', 0)}% |"
            )
        lines.append("")

    return lines


# ══════════════════════════════════════════════════════════════
# Telemetry Sections (new)
# ══════════════════════════════════════════════════════════════

def _format_telemetry_section(ta: Dict[str, Any]) -> List[str]:
    """Format the complete telemetry analysis section for one pool."""
    from core.telemetry_formatter import TelemetryFormatter
    
    lines = []
    pool_name = ta.get("pool_name", "unknown")

    lines.append(f"## Telemetry: {pool_name}")
    lines.append("")

    # Use unified formatter for core telemetry display (summary, per-thread analysis, latency)
    # This ensures console and markdown share the same formatting logic
    formatter = TelemetryFormatter(mode='markdown')
    
    # Convert analytics format to summary format expected by formatter
    summary = _convert_analytics_to_summary(ta)
    core_lines = formatter.format_telemetry(summary, pool_name)
    if core_lines:
        lines.extend(core_lines)

    # ── Additional "Nerd Stats" (markdown-only) ──
    # These sections provide detailed statistics beyond the core console preview
    
    # Sample Summary
    sample_summary = ta.get("sample_summary", {})
    if sample_summary:
        lines.extend(_format_sample_summary_section(sample_summary))

    # I/O Size Analysis
    io_size = ta.get("io_size_kb", {})
    if io_size:
        lines.extend(_format_io_size_section(io_size))

    # Anomaly Detection
    anomalies = ta.get("anomalies", [])
    anomaly_count = ta.get("anomaly_count", len(anomalies))
    lines.extend(_format_anomaly_section(anomalies, anomaly_count))

    # Capacity
    cap = ta.get("capacity_gib", {})
    if cap:
        lines.extend(_format_capacity_section(cap))

    return lines


def _convert_analytics_to_summary(ta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert analytics JSON format to summary format expected by TelemetryFormatter.
    
    The analytics format (from JSON) has a different structure than the
    live telemetry format. This normalizes it for the unified formatter.
    """
    phase_stats = ta.get("phase_stats", [])
    sample_summary = ta.get("sample_summary", {})
    
    # Build per_segment_steady_state from phase_stats
    per_segment = {}
    for ps in phase_stats:
        label = ps.get("label")
        if not label or ps.get("phase") == "idle":
            continue
        
        # Convert phase_stats format to per_segment format
        per_segment[label] = {
            "sample_count": ps.get("duration_samples", 0),
            "iops": {
                "write_all": ps.get("write_iops", {})
            },
            "bandwidth_mbps": {
                "write_all": ps.get("write_bandwidth_mbps", {})
            }
        }
    
    # Build all_samples with latency from phase_stats
    all_samples = {}
    if phase_stats:
        # Aggregate latency across phases
        write_latencies = []
        read_latencies = []
        for ps in phase_stats:
            w_lat = ps.get("write_latency_ms", {})
            r_lat = ps.get("read_latency_ms", {})
            if w_lat:
                write_latencies.append(w_lat)
            if r_lat:
                read_latencies.append(r_lat)
        
        # Use the first phase's latency as representative (or could aggregate)
        latency_ms = {}
        if write_latencies:
            latency_ms["total_wait_write"] = write_latencies[0]
        if read_latencies:
            latency_ms["total_wait_read"] = read_latencies[0]
        
        if latency_ms:
            all_samples["latency_ms"] = latency_ms
    
    return {
        "total_samples": sample_summary.get("total_samples", 0),
        "steady_state_samples": sample_summary.get("active_write_samples", 0) + sample_summary.get("active_read_samples", 0),
        "duration_seconds": ta.get("duration_seconds", 0),
        "per_segment_steady_state": per_segment,
        "all_samples": all_samples
    }


def _format_sample_summary_section(summary: Dict[str, Any]) -> List[str]:
    """Format the sample summary section (nerd stats)."""
    lines = []
    lines.append("### Sample Summary")
    lines.append("")
    lines.append(f"| Metric | Count | % of Total |")
    lines.append(f"|--------|------:|----------:|")
    lines.append(f"| Total Samples | {summary.get('total_samples', 0)} | 100% |")
    lines.append(
        f"| Active Write | {summary.get('active_write_samples', 0)} "
        f"| {summary.get('active_write_pct', 0)}% |"
    )
    lines.append(
        f"| Active Read | {summary.get('active_read_samples', 0)} "
        f"| {summary.get('active_read_pct', 0)}% |"
    )
    lines.append(
        f"| Idle | {summary.get('idle_samples', 0)} "
        f"| {summary.get('idle_pct', 0)}% |"
    )
    lines.append("")
    return lines


def _format_capacity_section(cap: Dict[str, Any]) -> List[str]:
    """Format the capacity section (nerd stats)."""
    lines = []
    lines.append("### Capacity")
    lines.append("")
    lines.append(f"| Metric | GiB |")
    lines.append(f"|--------|----:|")
    lines.append(f"| Start | {cap.get('start', 0):.2f} |")
    lines.append(f"| End | {cap.get('end', 0):.2f} |")
    lines.append(f"| Peak | {cap.get('max', 0):.2f} |")
    lines.append(f"| Min | {cap.get('min', 0):.2f} |")
    lines.append("")
    return lines


def _format_stats_row(label: str, stats: Dict[str, Any], unit: str = "") -> str:
    """Format a single stats dict as a markdown table row."""
    if not stats or stats.get("count", 0) == 0:
        return ""
    u = f" {unit}" if unit else ""
    return (
        f"| {label} "
        f"| {stats.get('count', 0)} "
        f"| {stats.get('mean', 0):,.1f}{u} "
        f"| {stats.get('median', 0):,.1f}{u} "
        f"| {stats.get('p99', 0):,.1f}{u} "
        f"| {stats.get('min', 0):,.1f}{u} "
        f"| {stats.get('max', 0):,.1f}{u} "
        f"| {stats.get('std_dev', 0):,.1f} "
        f"| {stats.get('cv_percent', 0):.1f}% |"
    )


def _format_iops_section(iops: Dict[str, Any]) -> List[str]:
    """Format IOPS statistics."""
    lines = []
    lines.append("### IOPS")
    lines.append("")
    lines.append("| Metric | Samples | Mean | Median | P99 | Min | Max | Std Dev | CV |")
    lines.append("|--------|--------:|-----:|-------:|----:|----:|----:|--------:|---:|")

    # All samples
    for key, label in [("write_ops", "Write (all)"), ("read_ops", "Read (all)"), ("total_ops", "Total (all)")]:
        row = _format_stats_row(label, iops.get("all_samples", {}).get(key, {}))
        if row:
            lines.append(row)

    # Active only
    for key, label in [("write_ops", "Write (active)"), ("read_ops", "Read (active)")]:
        row = _format_stats_row(label, iops.get("active_only", {}).get(key, {}))
        if row:
            lines.append(row)

    lines.append("")
    return lines


def _format_bandwidth_section(bw: Dict[str, Any]) -> List[str]:
    """Format bandwidth statistics."""
    lines = []
    lines.append("### Bandwidth (MB/s)")
    lines.append("")
    lines.append("| Metric | Samples | Mean | Median | P99 | Min | Max | Std Dev | CV |")
    lines.append("|--------|--------:|-----:|-------:|----:|----:|----:|--------:|---:|")

    for key, label in [("write", "Write (all)"), ("read", "Read (all)")]:
        row = _format_stats_row(label, bw.get("all_samples", {}).get(key, {}))
        if row:
            lines.append(row)

    for key, label in [("write", "Write (active)"), ("read", "Read (active)")]:
        row = _format_stats_row(label, bw.get("active_only", {}).get(key, {}))
        if row:
            lines.append(row)

    lines.append("")
    return lines


def _format_latency_section(lat: Dict[str, Any]) -> List[str]:
    """Format latency statistics."""
    lines = []
    lines.append("### Latency (ms)")
    lines.append("")
    lines.append("| Metric | Samples | Mean | Median | P99 | Min | Max | Std Dev | CV |")
    lines.append("|--------|--------:|-----:|-------:|----:|----:|----:|--------:|---:|")

    # Total wait
    for key, label in [("read", "Total Wait Read"), ("write", "Total Wait Write")]:
        row = _format_stats_row(label, lat.get("total_wait", {}).get(key, {}))
        if row:
            lines.append(row)

    # Disk wait
    for key, label in [("read", "Disk Wait Read"), ("write", "Disk Wait Write")]:
        row = _format_stats_row(label, lat.get("disk_wait", {}).get(key, {}))
        if row:
            lines.append(row)

    # Active only
    active = lat.get("active_only", {})
    for key, label in [
        ("total_wait_write", "Total Wait Write (active)"),
        ("total_wait_read", "Total Wait Read (active)"),
        ("disk_wait_read", "Disk Wait Read (active)"),
        ("disk_wait_write", "Disk Wait Write (active)"),
    ]:
        row = _format_stats_row(label, active.get(key, {}))
        if row:
            lines.append(row)

    lines.append("")
    return lines


def _format_queue_section(qd: Dict[str, Any]) -> List[str]:
    """Format queue depth statistics."""
    lines = []
    lines.append("### Queue Depths (ms)")
    lines.append("")
    lines.append("| Metric | Samples | Mean | Median | P99 | Min | Max | Std Dev | CV |")
    lines.append("|--------|--------:|-----:|-------:|----:|----:|----:|--------:|---:|")

    for key, label in [
        ("asyncq_wait_write", "Async Queue Write"),
        ("asyncq_wait_read", "Async Queue Read"),
        ("syncq_wait_write", "Sync Queue Write"),
        ("syncq_wait_read", "Sync Queue Read"),
    ]:
        row = _format_stats_row(label, qd.get(key, {}))
        if row:
            lines.append(row)

    # Active only
    active = qd.get("active_only", {})
    for key, label in [
        ("asyncq_wait_write", "Async Queue Write (active)"),
        ("syncq_wait_write", "Sync Queue Write (active)"),
    ]:
        row = _format_stats_row(label, active.get(key, {}))
        if row:
            lines.append(row)

    lines.append("")
    return lines


def _format_io_size_section(io_size: Dict[str, Any]) -> List[str]:
    """Format I/O size analysis."""
    lines = []
    lines.append("### I/O Size Analysis")
    lines.append("")

    write_stats = io_size.get("write_kb_per_op", {})
    read_stats = io_size.get("read_kb_per_op", {})

    if write_stats.get("count", 0) > 0 or read_stats.get("count", 0) > 0:
        lines.append("| Operation | Samples | Mean (KB) | Median (KB) | P99 (KB) | Min (KB) | Max (KB) | CV |")
        lines.append("|-----------|--------:|----------:|------------:|---------:|---------:|---------:|---:|")

        if write_stats.get("count", 0) > 0:
            lines.append(
                f"| Write | {write_stats['count']} "
                f"| {write_stats['mean']:,.1f} "
                f"| {write_stats['median']:,.1f} "
                f"| {write_stats['p99']:,.1f} "
                f"| {write_stats['min']:,.1f} "
                f"| {write_stats['max']:,.1f} "
                f"| {write_stats.get('cv_percent', 0):.1f}% |"
            )

        if read_stats.get("count", 0) > 0:
            lines.append(
                f"| Read | {read_stats['count']} "
                f"| {read_stats['mean']:,.1f} "
                f"| {read_stats['median']:,.1f} "
                f"| {read_stats['p99']:,.1f} "
                f"| {read_stats['min']:,.1f} "
                f"| {read_stats['max']:,.1f} "
                f"| {read_stats.get('cv_percent', 0):.1f}% |"
            )

        lines.append("")

    return lines


def _cv_rating(cv: float) -> str:
    """Generate a consistency rating based on CV%."""
    if cv < 10:
        return "✓ Excellent"
    elif cv < 20:
        return "✓ Good"
    elif cv < 30:
        return "~ Variable"
    else:
        return "⚠ High Variance"


def _format_anomaly_section(anomalies: List[Dict[str, Any]], count: int) -> List[str]:
    """Format anomaly detection results."""
    lines = []
    lines.append("### Anomaly Detection")
    lines.append("")

    if count == 0:
        lines.append("No statistical anomalies detected (threshold: z > 3.0).")
        lines.append("")
        return lines

    lines.append(f"**{count} anomalies detected** (z-score > 3.0):")
    lines.append("")

    # Group by metric
    by_metric: Dict[str, List[Dict]] = {}
    for a in anomalies:
        metric = a.get("metric", "unknown")
        by_metric.setdefault(metric, []).append(a)

    for metric, items in sorted(by_metric.items()):
        lines.append(f"**{metric}** ({len(items)} anomalies):")
        lines.append("")
        lines.append("| Timestamp | Value | Z-Score | Direction |")
        lines.append("|-----------|------:|--------:|-----------|")

        # Show top 10 per metric
        for a in items[:10]:
            ts = _truncate_timestamp(a.get("timestamp", ""))
            lines.append(
                f"| {ts} "
                f"| {a.get('value', 0):,.2f} "
                f"| {a.get('z_score', 0):.2f} "
                f"| {a.get('direction', '')} |"
            )

        if len(items) > 10:
            lines.append(f"| ... | ({len(items) - 10} more) | | |")

        lines.append("")

    return lines


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════

def _truncate_timestamp(ts: str) -> str:
    """Truncate ISO timestamp to readable form (no microseconds)."""
    if not ts:
        return ""
    return ts[:19]


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Generate markdown report from TN-Bench analytics")
    parser.add_argument("analytics_file", help="Path to analytics JSON file")
    parser.add_argument("-o", "--output", help="Output markdown file (default: stdout)")
    args = parser.parse_args()

    # Load analytics data
    with open(args.analytics_file, 'r') as f:
        analytics_data = json.load(f)

    # Generate report
    report = generate_markdown_report(analytics_data, args.analytics_file)

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
