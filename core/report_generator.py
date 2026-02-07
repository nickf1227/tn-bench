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
    lines = []
    pool_name = ta.get("pool_name", "unknown")

    lines.append(f"## Telemetry: {pool_name}")
    lines.append("")

    # ── Phase Analysis (PRIMARY) ──
    # Show per-phase steady-state analysis first as the main results
    phase_stats = ta.get("phase_stats", [])
    if phase_stats:
        lines.extend(_format_phase_section(phase_stats))

    # ── Sample Summary ──
    summary = ta.get("sample_summary", {})
    if summary:
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

    # ── I/O Size Analysis ──
    io_size = ta.get("io_size_kb", {})
    if io_size:
        lines.extend(_format_io_size_section(io_size))

    # ── Anomaly Detection ──
    anomalies = ta.get("anomalies", [])
    anomaly_count = ta.get("anomaly_count", len(anomalies))
    lines.extend(_format_anomaly_section(anomalies, anomaly_count))

    # ── Capacity ──
    cap = ta.get("capacity_gib", {})
    if cap:
        lines.append("### Capacity")
        lines.append("")
        lines.append(
            f"| Metric | GiB |"
        )
        lines.append(f"|--------|----:|")
        lines.append(f"| Start | {cap.get('start', 0):.2f} |")
        lines.append(f"| End | {cap.get('end', 0):.2f} |")
        lines.append(f"| Peak | {cap.get('max', 0):.2f} |")
        lines.append(f"| Min | {cap.get('min', 0):.2f} |")
        lines.append("")

    # ── Detailed Aggregate Statistics (collapsible/secondary) ──
    lines.append("### Detailed Aggregate Statistics")
    lines.append("")
    lines.append("*Complete statistics across all samples for reference. See Per-Phase Analysis above for steady-state metrics.*")
    lines.append("")

    # ── IOPS ──
    iops = ta.get("iops", {})
    if iops:
        lines.extend(_format_iops_section(iops))

    # ── Bandwidth ──
    bw = ta.get("bandwidth_mbps", {})
    if bw:
        lines.extend(_format_bandwidth_section(bw))

    # ── Latency ──
    lat = ta.get("latency_ms", {})
    if lat:
        lines.extend(_format_latency_section(lat))

    # ── Queue Depths ──
    qd = ta.get("queue_depths", {})
    if qd:
        lines.extend(_format_queue_section(qd))

    # ── Observations ──
    observations = ta.get("observations", [])
    if observations:
        lines.append("### Telemetry Observations")
        lines.append("")
        for obs in observations:
            lines.append(f"- **{obs.get('category', '')}:** {obs.get('description', '')}")
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


def _format_phase_section(phase_stats: List[Dict[str, Any]]) -> List[str]:
    """Format phase detection results as the primary steady-state analysis."""
    lines = []
    lines.append("### Per-Thread-Count Steady-State Analysis")
    lines.append("")
    lines.append("Consistent performance analysis per detected benchmark phase.")
    lines.append("")

    # Filter to active phases with sufficient samples
    active_phases = [
        ps for ps in phase_stats
        if ps.get("phase") != "idle" and ps.get("duration_samples", 0) >= 3
    ]

    if not active_phases:
        lines.append("*No steady-state phases detected with sufficient samples (minimum 3).")
        lines.append("")
        return lines

    # Group phases by dominant operation type and sort by thread count inference
    # For now, we'll label them sequentially as detected
    for i, ps in enumerate(active_phases, 1):
        phase_name = ps.get("phase", "unknown").upper()
        dur = ps.get("duration_samples", 0)
        label = ps.get("label", f"Phase-{i}")

        # Create phase label with thread count if available
        if label:
            lines.append(f"#### {label} ({dur} samples)")
        else:
            lines.append(f"#### Phase {i}: {phase_name} ({dur} samples)")
        lines.append("")

        # Build unified table with all metrics
        lines.append("| Metric | Operation | Mean | P99 | Std Dev | CV% | Rating |")
        lines.append("|--------|-----------|------:|-----:|--------:|-----:|--------|")

        # Write metrics
        w_iops = ps.get("write_iops", {})
        w_bw = ps.get("write_bandwidth_mbps", {})
        w_lat = ps.get("write_latency_ms", {})

        if w_iops.get("count", 0) > 0:
            cv = w_iops.get("cv_percent", 0)
            rating = _cv_rating(cv)
            lines.append(
                f"| IOPS | Write | {w_iops['mean']:,.0f} | {w_iops['p99']:,.0f} | "
                f"{w_iops['std_dev']:,.0f} | {cv:.1f}% | {rating} |"
            )
        if w_bw.get("count", 0) > 0:
            cv = w_bw.get("cv_percent", 0)
            rating = _cv_rating(cv)
            lines.append(
                f"| Bandwidth (MB/s) | Write | {w_bw['mean']:,.1f} | {w_bw['p99']:,.1f} | "
                f"{w_bw['std_dev']:,.1f} | {cv:.1f}% | {rating} |"
            )
        if w_lat.get("count", 0) > 0:
            cv = w_lat.get("cv_percent", 0)
            rating = _cv_rating(cv)
            lines.append(
                f"| Latency (ms) | Write | {w_lat['mean']:.2f} | {w_lat['p99']:.2f} | "
                f"{w_lat['std_dev']:.2f} | {cv:.1f}% | {rating} |"
            )

        # Read metrics
        r_iops = ps.get("read_iops", {})
        r_bw = ps.get("read_bandwidth_mbps", {})
        r_lat = ps.get("read_latency_ms", {})

        if r_iops.get("count", 0) > 0:
            cv = r_iops.get("cv_percent", 0)
            rating = _cv_rating(cv)
            lines.append(
                f"| IOPS | Read | {r_iops['mean']:,.0f} | {r_iops['p99']:,.0f} | "
                f"{r_iops['std_dev']:,.0f} | {cv:.1f}% | {rating} |"
            )
        if r_bw.get("count", 0) > 0:
            cv = r_bw.get("cv_percent", 0)
            rating = _cv_rating(cv)
            lines.append(
                f"| Bandwidth (MB/s) | Read | {r_bw['mean']:,.1f} | {r_bw['p99']:,.1f} | "
                f"{r_bw['std_dev']:,.1f} | {cv:.1f}% | {rating} |"
            )
        if r_lat.get("count", 0) > 0:
            cv = r_lat.get("cv_percent", 0)
            rating = _cv_rating(cv)
            lines.append(
                f"| Latency (ms) | Read | {r_lat['mean']:.2f} | {r_lat['p99']:.2f} | "
                f"{r_lat['std_dev']:.2f} | {cv:.1f}% | {rating} |"
            )

        lines.append("")

    # Add phase timeline summary
    lines.append("#### Phase Timeline Summary")
    lines.append("")
    lines.append("| # | Phase | Samples | Start | End |")
    lines.append("|---|-------|--------:|-------|-----|")
    for i, ps in enumerate(phase_stats, 1):
        phase = ps.get("phase", "?").upper()
        dur = ps.get("duration_samples", 0)
        start = _truncate_timestamp(ps.get("start_time", ""))
        end = _truncate_timestamp(ps.get("end_time", ""))
        lines.append(f"| {i} | {phase} | {dur} | {start} | {end} |")
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
