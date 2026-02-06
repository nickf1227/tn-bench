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
    
    def to_dict(self) -> dict:
        """Convert telemetry to dictionary for JSON serialization."""
        return {
            "pool_name": self.pool_name,
            "start_time": self.start_time,
            "start_time_iso": self.start_time_iso,
            "end_time": self.end_time,
            "end_time_iso": self.end_time_iso,
            "duration_seconds": round(self.end_time - self.start_time, 2) if self.end_time else None,
            "warmup_iterations": self.warmup_iterations,
            "cooldown_iterations": self.cooldown_iterations,
            "total_samples": len(self.samples),
            "samples": [asdict(s) for s in self.samples]
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


def calculate_zpool_iostat_summary(telemetry: ZpoolIostatTelemetry) -> dict:
    """
    Calculate summary statistics from zpool iostat telemetry data.
    
    Returns:
        Dictionary with summary statistics
    """
    if not telemetry or not telemetry.samples:
        return {}
        
    samples = telemetry.samples
    
    def avg(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0
        
    def max_val(values: List[float]) -> float:
        return max(values) if values else 0
        
    def min_val(values: List[float]) -> float:
        return min(values) if values else 0
    
    read_ops = [s.operations_read for s in samples]
    write_ops = [s.operations_write for s in samples]
    
    summary = {
        "pool_name": telemetry.pool_name,
        "total_samples": len(samples),
        "duration_seconds": round(telemetry.end_time - telemetry.start_time, 2) if telemetry.end_time else None,
        "operations_per_second": {
            "read_avg": round(avg(read_ops), 2),
            "read_max": round(max_val(read_ops), 2),
            "read_min": round(min_val(read_ops), 2),
            "write_avg": round(avg(write_ops), 2),
            "write_max": round(max_val(write_ops), 2),
            "write_min": round(min_val(write_ops), 2),
            "total_avg": round(avg(read_ops) + avg(write_ops), 2)
        }
    }
    
    return summary
