"""
TN-Bench Markdown Report Generator
Generates human-readable markdown reports from analytics JSON.
Part of TN-Bench 2.1
"""

import json
import argparse
from datetime import datetime
from typing import Dict, Any, Optional


def generate_markdown_report(analytics_data: Dict[str, Any], source_file: str) -> str:
    """Generate a markdown report from analytics data."""
    lines = []
    
    # Header
    lines.append("# TN-Bench Analytics Report")
    lines.append("")
    lines.append(f"**Source:** `{source_file}`")  
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Pool Analyses
    for pool in analytics_data.get("pool_analyses", []):
        lines.extend(_format_pool_section(pool))
    
    # Disk Comparison
    lines.extend(_format_disk_section(analytics_data.get("disk_comparison", {})))
    
    return "\n".join(lines)


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
