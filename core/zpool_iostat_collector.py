"""
ZPool Iostat Collector for TN-Bench.

Collects zpool iostat telemetry during pool benchmarks.
Runs in background thread, capturing performance metrics.
"""

import subprocess
import threading
import time
import signal
import re
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from utils import print_info, print_success, print_error, print_warning, color_text


@dataclass
class ZpoolIostatSample:
    """A single sample of zpool iostat data."""
    timestamp: float
    timestamp_iso: str
    pool_name: str
    capacity_used: str
    capacity_avail: str
    operations_read: float
    operations_write: float
    bandwidth_read: str
    bandwidth_write: str
    total_wait_read: str
    total_wait_write: str
    disk_wait_read: str
    disk_wait_write: str
    syncq_wait_read: str
    syncq_wait_write: str
    asyncq_wait_read: str
    asyncq_wait_write: str
    scrub_wait: str
    trim_wait: str


@dataclass
class ZpoolIostatTelemetry:
    """Complete telemetry data for a benchmark run."""
    pool_name: str
    start_time: float
    start_time_iso: str
    end_time: Optional[float] = None
    end_time_iso: Optional[str] = None
    warmup_iterations: int = 0
    cooldown_iterations: int = 0
    samples: List[ZpoolIostatSample] = field(default_factory=list)
    
    def to_dict(self, sample_interval: int = 1) -> dict:
        """
        Convert telemetry to dictionary for JSON serialization.
        
        Args:
            sample_interval: Keep every Nth sample (default: 1 = all samples).
                           Use 5 to keep every 5th sample, 10 for every 10th, etc.
        """
        # Slice samples based on interval (keep every Nth)
        downsampled = self.samples[::sample_interval] if sample_interval > 1 else self.samples
        
        return {
            "pool_name": self.pool_name,
            "start_time": self.start_time,
            "start_time_iso": self.start_time_iso,
            "end_time": self.end_time,
            "end_time_iso": self.end_time_iso,
            "duration_seconds": round(self.end_time - self.start_time, 2) if self.end_time else None,
            "warmup_iterations": self.warmup_iterations,
            "cooldown_iterations": self.cooldown_iterations,
            "total_samples_collected": len(self.samples),
            "sample_interval": sample_interval,
            "samples_in_output": len(downsampled),
            "samples": [asdict(s) for s in downsampled]
        }


class ZpoolIostatCollector:
    """
    Background collector for zpool iostat telemetry.
    
    Usage:
        collector = ZpoolIostatCollector("tank", interval=1)
        collector.start(warmup_iterations=3)
        # ... run benchmark ...
        telemetry = collector.stop(cooldown_iterations=3)
    """
    
    def __init__(self, pool_name: str, interval: int = 1, extended_stats: bool = True):
        """
        Initialize the zpool iostat collector.
        
        Args:
            pool_name: Name of the ZFS pool to monitor
            interval: Sampling interval in seconds (default: 1)
            extended_stats: Include extended latency statistics
        """
        self.pool_name = pool_name
        self.interval = interval
        self.extended_stats = extended_stats
        self.telemetry: Optional[ZpoolIostatTelemetry] = None
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._warmup_count = 0
        self._cooldown_count = 0
        self._warmup_target = 0
        self._cooldown_target = 0
        self._benchmark_active = False
        
    def _build_command(self) -> List[str]:
        """Build the zpool iostat command."""
        cmd = ["zpool", "iostat", "-H"]  # -H for scripted mode (no headers)
        
        if self.extended_stats:
            cmd.append("-l")  # Include latency statistics
            
        cmd.extend([self.pool_name, str(self.interval)])
        
        return cmd
    
    def _parse_value_with_suffix(self, value: str) -> float:
        """
        Parse a value that may have a unit suffix (K, M, G).
        
        Args:
            value: String like "1.77K", "292M", "0", etc.
            
        Returns:
            Float value (e.g., 1770.0 for "1.77K")
        """
        if not value or value == "-":
            return 0.0
            
        value = value.strip()
        suffix_multipliers = {
            'K': 1_000,
            'M': 1_000_000,
            'G': 1_000_000_000,
            'T': 1_000_000_000_000,
        }
        
        # Check if last character is a suffix
        if value[-1] in suffix_multipliers:
            suffix = value[-1]
            number = value[:-1]
            return float(number) * suffix_multipliers[suffix]
        else:
            return float(value)
    
    def _parse_line(self, line: str) -> Optional[ZpoolIostatSample]:
        """
        Parse a line of zpool iostat output.
        
        Returns:
            ZpoolIostatSample if parsed successfully, None otherwise
        """
        parts = line.strip().split()
        if len(parts) < 7:
            return None
            
        try:
            # Basic format: pool capacity_used capacity_avail ops_r ops_w bw_r bw_w ...
            timestamp = time.time()
            
            # Handle extended stats format
            if self.extended_stats and len(parts) >= 15:
                return ZpoolIostatSample(
                    timestamp=timestamp,
                    timestamp_iso=datetime.fromtimestamp(timestamp).isoformat(),
                    pool_name=parts[0],
                    capacity_used=parts[1],
                    capacity_avail=parts[2],
                    operations_read=self._parse_value_with_suffix(parts[3]),
                    operations_write=self._parse_value_with_suffix(parts[4]),
                    bandwidth_read=parts[5],
                    bandwidth_write=parts[6],
                    total_wait_read=parts[7],
                    disk_wait_read=parts[8],
                    syncq_wait_read=parts[9],
                    asyncq_wait_read=parts[10],
                    total_wait_write=parts[11],
                    disk_wait_write=parts[12],
                    syncq_wait_write=parts[13],
                    asyncq_wait_write=parts[14],
                    scrub_wait=parts[15] if len(parts) > 15 else "-",
                    trim_wait=parts[16] if len(parts) > 16 else "-"
                )
            else:
                # Basic format without extended stats
                return ZpoolIostatSample(
                    timestamp=timestamp,
                    timestamp_iso=datetime.fromtimestamp(timestamp).isoformat(),
                    pool_name=parts[0],
                    capacity_used=parts[1],
                    capacity_avail=parts[2],
                    operations_read=self._parse_value_with_suffix(parts[3]),
                    operations_write=self._parse_value_with_suffix(parts[4]),
                    bandwidth_read=parts[5],
                    bandwidth_write=parts[6],
                    total_wait_read="-",
                    total_wait_write="-",
                    disk_wait_read="-",
                    disk_wait_write="-",
                    syncq_wait_read="-",
                    syncq_wait_write="-",
                    asyncq_wait_read="-",
                    asyncq_wait_write="-",
                    scrub_wait="-",
                    trim_wait="-"
                )
        except (ValueError, IndexError) as e:
            print_warning(f"Failed to parse zpool iostat line: {line.strip()} - {e}")
            return None
    
    def _collection_loop(self):
        """Main collection loop running in background thread."""
        cmd = self._build_command()
        print_info(f"Starting zpool iostat collection for pool '{self.pool_name}' (interval: {self.interval}s)")
        
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            while not self._stop_event.is_set() and self._process.poll() is None:
                try:
                    line = self._process.stdout.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    
                    # Skip header lines
                    if line.strip().startswith("capacity") or line.strip().startswith("operations"):
                        continue
                    
                    sample = self._parse_line(line)
                    if sample and self.telemetry:
                        # Track warmup/cooldown/benchmark phases
                        if not self._benchmark_active and self._warmup_count < self._warmup_target:
                            self._warmup_count += 1
                        elif self._benchmark_active:
                            pass  # Regular benchmark sample
                        elif self._cooldown_count < self._cooldown_target:
                            self._cooldown_count += 1
                            
                        self.telemetry.samples.append(sample)
                        
                except Exception as e:
                    if not self._stop_event.is_set():
                        print_warning(f"Error reading zpool iostat output: {e}")
                    
        except Exception as e:
            if not self._stop_event.is_set():
                print_error(f"Zpool iostat collection error: {e}")
        finally:
            self._cleanup_process()
            
    def _cleanup_process(self):
        """Clean up the subprocess."""
        if self._process:
            try:
                # Terminate gracefully first
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if necessary
                    self._process.kill()
                    self._process.wait()
            except Exception:
                pass
            finally:
                self._process = None
    
    def start(self, warmup_iterations: int = 3) -> bool:
        """
        Start the zpool iostat collector.
        
        Args:
            warmup_iterations: Number of samples to collect before benchmark starts
            
        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            print_warning("Zpool iostat collector already running")
            return False
            
        self._warmup_target = warmup_iterations
        self._warmup_count = 0
        self._cooldown_count = 0
        self._benchmark_active = False
        self._stop_event.clear()
        
        start_time = time.time()
        self.telemetry = ZpoolIostatTelemetry(
            pool_name=self.pool_name,
            start_time=start_time,
            start_time_iso=datetime.fromtimestamp(start_time).isoformat(),
            warmup_iterations=warmup_iterations
        )
        
        self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._thread.start()
        self._running = True
        
        # Wait for warmup if specified
        if warmup_iterations > 0:
            print_info(f"Warming up zpool iostat collector ({warmup_iterations} samples)...")
            while self._warmup_count < warmup_iterations:
                if not self._running or self._stop_event.is_set():
                    return False
                time.sleep(0.1)
            print_success("Zpool iostat collector warmup complete")
        
        return True
    
    def signal_benchmark_start(self):
        """Signal that the benchmark is starting (transition from warmup to active)."""
        self._benchmark_active = True
        print_info("Zpool iostat collector: benchmark phase started")
        
    def signal_benchmark_end(self):
        """Signal that the benchmark has ended (transition to cooldown)."""
        self._benchmark_active = False
        print_info("Zpool iostat collector: benchmark phase ended")
    
    def stop(self, cooldown_iterations: int = 3) -> Optional[ZpoolIostatTelemetry]:
        """
        Stop the zpool iostat collector.
        
        Args:
            cooldown_iterations: Number of samples to collect after benchmark ends
            
        Returns:
            ZpoolIostatTelemetry object with all collected data, or None if not running
        """
        if not self._running:
            print_warning("Zpool iostat collector not running")
            return self.telemetry
            
        self._cooldown_target = cooldown_iterations
        
        # Wait for cooldown if specified
        if cooldown_iterations > 0 and self.telemetry:
            print_info(f"Cooling down zpool iostat collector ({cooldown_iterations} samples)...")
            current_count = len(self.telemetry.samples)
            target = current_count + cooldown_iterations
            while len(self.telemetry.samples) < target:
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)
            print_success("Zpool iostat collector cooldown complete")
        
        self._stop_event.set()
        self._running = False
        
        if self.telemetry:
            self.telemetry.cooldown_iterations = cooldown_iterations
            self.telemetry.end_time = time.time()
            self.telemetry.end_time_iso = datetime.fromtimestamp(
                self.telemetry.end_time
            ).isoformat()
        
        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            
        self._cleanup_process()
        
        if self.telemetry:
            print_success(f"Zpool iostat collection complete: {len(self.telemetry.samples)} samples")
            
        return self.telemetry
    
    def is_running(self) -> bool:
        """Check if the collector is currently running."""
        return self._running and self._thread and self._thread.is_alive()
    
    def get_sample_count(self) -> int:
        """Get the current number of collected samples."""
        return len(self.telemetry.samples) if self.telemetry else 0


class ZpoolIostatCollectorWithContext:
    """
    Context manager for easy zpool iostat collection integration.
    
    Usage:
        with ZpoolIostatCollectorWithContext("tank", warmup=3, cooldown=3) as collector:
            collector.signal_benchmark_start()
            # ... run benchmark ...
            collector.signal_benchmark_end()
        # telemetry is automatically available
    """
    
    def __init__(self, pool_name: str, interval: int = 1, 
                 warmup: int = 3, cooldown: int = 3,
                 extended_stats: bool = True):
        self.pool_name = pool_name
        self.interval = interval
        self.warmup = warmup
        self.cooldown = cooldown
        self.extended_stats = extended_stats
        self.collector = ZpoolIostatCollector(pool_name, interval, extended_stats)
        self.telemetry: Optional[ZpoolIostatTelemetry] = None
        
    def __enter__(self):
        self.collector.start(warmup_iterations=self.warmup)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.telemetry = self.collector.stop(cooldown_iterations=self.cooldown)
        return False  # Don't suppress exceptions
        
    def signal_benchmark_start(self):
        """Signal benchmark start."""
        self.collector.signal_benchmark_start()
        
    def signal_benchmark_end(self):
        """Signal benchmark end."""
        self.collector.signal_benchmark_end()


def _calculate_stats(values: List[float]) -> dict:
    """Calculate comprehensive statistics for a list of values."""
    if not values:
        return {}
    
    n = len(values)
    sorted_vals = sorted(values)
    
    # Mean
    mean = sum(values) / n
    
    # Median
    mid = n // 2
    median = sorted_vals[mid] if n % 2 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    
    # Percentiles
    def percentile(p: float) -> float:
        idx = (p / 100) * (n - 1)
        lower = int(idx)
        upper = min(lower + 1, n - 1)
        frac = idx - lower
        return sorted_vals[lower] + frac * (sorted_vals[upper] - sorted_vals[lower])
    
    p50 = percentile(50)
    p90 = percentile(90)
    p95 = percentile(95)
    p99 = percentile(99)
    
    # Standard deviation
    variance = sum((x - mean) ** 2 for x in values) / n
    std_dev = variance ** 0.5
    
    # Coefficient of variation
    cv_percent = (std_dev / mean * 100) if mean != 0 else 0
    
    return {
        "count": n,
        "mean": mean,
        "median": median,
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "p50": p50,
        "p90": p90,
        "p95": p95,
        "p99": p99,
        "std_dev": std_dev,
        "cv_percent": cv_percent
    }


def calculate_zpool_iostat_summary(telemetry: ZpoolIostatTelemetry) -> dict:
    """
    Calculate comprehensive summary statistics from zpool iostat telemetry data.
    
    Returns:
        Dictionary with summary statistics including IOPS, bandwidth, and latency
    """
    if not telemetry or not telemetry.samples:
        return {}
        
    samples = telemetry.samples
    
    # Extract raw values
    read_ops = [s.operations_read for s in samples]
    write_ops = [s.operations_write for s in samples]
    total_ops = [r + w for r, w in zip(read_ops, write_ops)]
    
    # Bandwidth parsing (convert to MB/s)
    def parse_bandwidth(bw_str: str) -> float:
        """Parse bandwidth string to MB/s."""
        if not bw_str or bw_str == "-":
            return 0.0
        try:
            bw_str = bw_str.strip()
            multipliers = {'K': 0.001, 'M': 1.0, 'G': 1000.0}
            if bw_str[-1] in multipliers:
                return float(bw_str[:-1]) * multipliers[bw_str[-1]]
            return float(bw_str) / 1_000_000  # Assume bytes
        except (ValueError, IndexError):
            return 0.0
    
    read_bw = [parse_bandwidth(s.bandwidth_read) for s in samples]
    write_bw = [parse_bandwidth(s.bandwidth_write) for s in samples]
    
    # Latency parsing (convert to ms)
    def parse_latency(lat_str: str) -> float:
        """Parse latency string to milliseconds."""
        if not lat_str or lat_str == "-":
            return 0.0
        try:
            lat_str = lat_str.strip()
            if lat_str.endswith('ms'):
                return float(lat_str[:-2])
            elif lat_str.endswith('us'):
                return float(lat_str[:-2]) / 1000.0
            elif lat_str.endswith('s'):
                return float(lat_str[:-1]) * 1000.0
            return float(lat_str)
        except (ValueError, IndexError):
            return 0.0
    
    total_wait_read = [parse_latency(s.total_wait_read) for s in samples if parse_latency(s.total_wait_read) > 0]
    total_wait_write = [parse_latency(s.total_wait_write) for s in samples if parse_latency(s.total_wait_write) > 0]
    disk_wait_read = [parse_latency(s.disk_wait_read) for s in samples if parse_latency(s.disk_wait_read) > 0]
    disk_wait_write = [parse_latency(s.disk_wait_write) for s in samples if parse_latency(s.disk_wait_write) > 0]
    
    # Separate active vs idle samples (idle = both read and write IOPS are 0)
    active_samples = [(r, w, rb, wb) for r, w, rb, wb in zip(read_ops, write_ops, read_bw, write_bw) if r > 0 or w > 0]
    if active_samples:
        active_read_ops = [s[0] for s in active_samples]
        active_write_ops = [s[1] for s in active_samples]
        active_read_bw = [s[2] for s in active_samples]
        active_write_bw = [s[3] for s in active_samples]
    else:
        active_read_ops, active_write_ops, active_read_bw, active_write_bw = [], [], [], []
    
    summary = {
        "pool_name": telemetry.pool_name,
        "total_samples": len(samples),
        "duration_seconds": round(telemetry.end_time - telemetry.start_time, 2) if telemetry.end_time else None,
        "iops": {
            "read_all": _calculate_stats(read_ops),
            "write_all": _calculate_stats(write_ops),
            "total_all": _calculate_stats(total_ops),
            "read_active": _calculate_stats(active_read_ops) if active_read_ops else None,
            "write_active": _calculate_stats(active_write_ops) if active_write_ops else None,
        },
        "bandwidth_mbps": {
            "read_all": _calculate_stats(read_bw),
            "write_all": _calculate_stats(write_bw),
            "read_active": _calculate_stats(active_read_bw) if active_read_bw else None,
            "write_active": _calculate_stats(active_write_bw) if active_write_bw else None,
        },
        "latency_ms": {
            "total_wait_read": _calculate_stats(total_wait_read) if total_wait_read else None,
            "total_wait_write": _calculate_stats(total_wait_write) if total_wait_write else None,
            "disk_wait_read": _calculate_stats(disk_wait_read) if disk_wait_read else None,
            "disk_wait_write": _calculate_stats(disk_wait_write) if disk_wait_write else None,
        }
    }
    
    return summary
