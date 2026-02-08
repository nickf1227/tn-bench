"""
ZPool Iostat Collector for tn-bench.

Collects zpool iostat telemetry during pool benchmarks.
Runs in background thread, capturing performance metrics.

Includes phase detection to automatically identify:
- IDLE: No I/O or very low activity
- WARMUP: Initial ramp-up at start of a workload segment
- STEADY_STATE: Consistent high activity (primary analysis target)
- COOLDOWN: Activity winding down at end of a workload segment
- TRANSITION: Between thread count or workload changes
"""

import subprocess
import threading
import time
import signal
import re
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# Try importing project utils; fall back to no-ops for standalone testing
# ---------------------------------------------------------------------------
try:
    from utils import print_info, print_success, print_error, print_warning, color_text
except ImportError:
    def print_info(msg): print(f"[INFO] {msg}")
    def print_success(msg): print(f"[OK]   {msg}")
    def print_error(msg): print(f"[ERR]  {msg}")
    def print_warning(msg): print(f"[WARN] {msg}")
    def color_text(text, _color=""): return text


# ═══════════════════════════════════════════════════════════════════════════
# Phase Detection
# ═══════════════════════════════════════════════════════════════════════════

class Phase(str, Enum):
    """Workload phases detected from IOPS patterns."""
    IDLE = "idle"
    WARMUP = "warmup"
    STEADY_STATE = "steady_state"
    COOLDOWN = "cooldown"
    TRANSITION = "transition"


@dataclass
class PhaseSpan:
    """A contiguous span where the workload was in a single phase."""
    phase: str               # Phase enum value
    start_time: float        # epoch seconds
    end_time: float          # epoch seconds (updated on every sample)
    start_index: int         # index into samples list
    end_index: int           # inclusive
    sample_count: int = 0
    # Optional label for what workload segment this belongs to
    segment_label: str = ""

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "sample_count": self.sample_count,
            "duration_seconds": round(self.duration, 2),
            "segment_label": self.segment_label,
        }


class PhaseDetector:
    """
    Detects workload phases from streaming IOPS samples.

    Algorithm overview (rolling-window based):
    1. Keep a rolling window of the last *window_size* total-IOPS values.
    2. Classify the current window into a phase:
       - **IDLE**: mean IOPS < idle_threshold
       - **STEADY_STATE**: mean IOPS >= active_threshold AND CV% of window < steady_cv_max
       - **WARMUP**: mean IOPS is rising (current > previous window mean by ramp_ratio)
         and we were previously IDLE or TRANSITION
       - **COOLDOWN**: mean IOPS is falling and we were previously STEADY_STATE
       - **TRANSITION**: everything else (between segments, mixed signals)
    3. A hysteresis counter prevents flapping: a phase must hold for
       *min_hold_samples* consecutive classifications before being committed.
    """

    def __init__(
        self,
        *,
        idle_threshold: float = 500,
        active_threshold: float = 5000,
        steady_cv_max: float = 50.0,
        window_size: int = 3,
        min_hold_samples: int = 2,
    ):
        self.idle_threshold = idle_threshold
        self.active_threshold = active_threshold
        self.steady_cv_max = steady_cv_max
        self.window_size = window_size
        self.min_hold_samples = min_hold_samples

        # Internal state
        self._iops_history: List[float] = []
        self._current_phase = Phase.IDLE
        self._candidate_phase: Optional[Phase] = None
        self._candidate_count: int = 0
        self._prev_window_mean: float = 0.0

        # Completed & current spans
        self.spans: List[PhaseSpan] = []
        self._current_span: Optional[PhaseSpan] = None
        self._sample_index: int = 0

        # External segment label (set by benchmark harness)
        self._segment_label: str = ""

    # -- public API ----------------------------------------------------------

    def set_segment_label(self, label: str):
        """Set a label for the current workload segment (e.g. '8T-write')."""
        self._segment_label = label

    def push(self, total_iops: float, timestamp: float) -> Phase:
        """
        Feed one sample and return the (possibly updated) current phase.
        """
        self._iops_history.append(total_iops)

        raw = self._classify_window()

        # Hysteresis: require min_hold_samples consecutive same-classification
        if raw != self._candidate_phase:
            self._candidate_phase = raw
            self._candidate_count = 1
        else:
            self._candidate_count += 1

        if self._candidate_count >= self.min_hold_samples and raw != self._current_phase:
            self._commit_phase(raw, timestamp)

        # Always update the running span
        if self._current_span:
            self._current_span.end_time = timestamp
            self._current_span.end_index = self._sample_index
            self._current_span.sample_count += 1
        else:
            self._start_span(self._current_phase, timestamp)

        self._sample_index += 1
        return self._current_phase

    @property
    def current_phase(self) -> Phase:
        return self._current_phase

    def finalize(self) -> List[PhaseSpan]:
        """Close the last span and return all spans."""
        if self._current_span:
            self.spans.append(self._current_span)
            self._current_span = None
        return self.spans

    def get_steady_state_indices(self) -> List[int]:
        """Return sample indices classified as STEADY_STATE."""
        indices: List[int] = []
        all_spans = self.spans + ([self._current_span] if self._current_span else [])
        for span in all_spans:
            if span.phase == Phase.STEADY_STATE.value:
                indices.extend(range(span.start_index, span.end_index + 1))
        return indices

    # -- internals -----------------------------------------------------------

    def _classify_window(self) -> Phase:
        """Classify the current rolling window into a raw phase."""
        window = self._iops_history[-self.window_size:]
        if not window:
            return Phase.IDLE

        mean = sum(window) / len(window)

        # Idle check
        if mean < self.idle_threshold:
            self._prev_window_mean = mean
            return Phase.IDLE

        # Active: check variance for steady-state
        if mean >= self.active_threshold and len(window) >= self.window_size:
            variance = sum((x - mean) ** 2 for x in window) / len(window)
            std = variance ** 0.5
            cv = (std / mean * 100) if mean > 0 else 0

            if cv < self.steady_cv_max:
                self._prev_window_mean = mean
                return Phase.STEADY_STATE

        # Rising from idle/transition → warmup
        if self._current_phase in (Phase.IDLE, Phase.TRANSITION) and mean > self._prev_window_mean * 1.5 and mean >= self.idle_threshold:
            self._prev_window_mean = mean
            return Phase.WARMUP

        # Falling from steady-state → cooldown
        if self._current_phase == Phase.STEADY_STATE and mean < self._prev_window_mean * 0.5:
            self._prev_window_mean = mean
            return Phase.COOLDOWN

        self._prev_window_mean = mean
        return Phase.TRANSITION

    def _commit_phase(self, new_phase: Phase, timestamp: float):
        """Commit a phase transition."""
        # Close existing span
        if self._current_span:
            self.spans.append(self._current_span)
            self._current_span = None

        self._current_phase = new_phase
        self._start_span(new_phase, timestamp)

    def _start_span(self, phase: Phase, timestamp: float):
        self._current_span = PhaseSpan(
            phase=phase.value,
            start_time=timestamp,
            end_time=timestamp,
            start_index=self._sample_index,
            end_index=self._sample_index,
            sample_count=1,
            segment_label=self._segment_label,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════

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
    # Phase detection fields (populated post-hoc or in real-time)
    phase: str = ""
    segment_label: str = ""


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
    phase_spans: List[PhaseSpan] = field(default_factory=list)

    def to_dict(self, sample_interval: int = 1) -> dict:
        """
        Convert telemetry to dictionary for JSON serialization.

        Args:
            sample_interval: Keep every Nth sample (default: 1 = all samples).
                           Use 5 to keep every 5th sample, 10 for every 10th, etc.
        """
        # Slice samples based on interval (keep every Nth)
        downsampled = self.samples[::sample_interval] if sample_interval > 1 else self.samples

        # Phase summary
        phase_summary = _build_phase_summary(self.phase_spans, self.samples)

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
            "phase_detection": phase_summary,
            "samples": [asdict(s) for s in downsampled],
        }

    def get_samples_by_phase(self, phase: Phase) -> List[ZpoolIostatSample]:
        """Return only samples belonging to the given phase."""
        target = phase.value
        return [s for s in self.samples if s.phase == target]

    def get_steady_state_samples(self) -> List[ZpoolIostatSample]:
        """Convenience: return only steady-state samples."""
        return self.get_samples_by_phase(Phase.STEADY_STATE)


def _build_phase_summary(spans: List[PhaseSpan], samples: List[ZpoolIostatSample]) -> dict:
    """Build a summary dict describing detected phases."""
    if not spans:
        return {}

    phase_durations: Dict[str, float] = {}
    phase_counts: Dict[str, int] = {}
    for sp in spans:
        phase_durations[sp.phase] = phase_durations.get(sp.phase, 0) + sp.duration
        phase_counts[sp.phase] = phase_counts.get(sp.phase, 0) + sp.sample_count

    total_duration = sum(phase_durations.values())

    breakdown = {}
    for phase_name in [p.value for p in Phase]:
        dur = phase_durations.get(phase_name, 0)
        cnt = phase_counts.get(phase_name, 0)
        breakdown[phase_name] = {
            "duration_seconds": round(dur, 2),
            "sample_count": cnt,
            "percent_of_total": round(dur / total_duration * 100, 1) if total_duration > 0 else 0,
        }

    return {
        "total_phases_detected": len(spans),
        "breakdown": breakdown,
        "spans": [sp.to_dict() for sp in spans],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Collector
# ═══════════════════════════════════════════════════════════════════════════

class ZpoolIostatCollector:
    """
    Background collector for zpool iostat telemetry.

    Usage:
        collector = ZpoolIostatCollector("tank", interval=1)
        collector.start(warmup_iterations=3)
        # ... run benchmark ...
        telemetry = collector.stop(cooldown_iterations=3)
    """

    def __init__(self, pool_name: str, interval: int = 1, extended_stats: bool = True,
                 phase_detection: bool = True):
        """
        Initialize the zpool iostat collector.

        Args:
            pool_name: Name of the ZFS pool to monitor
            interval: Sampling interval in seconds (default: 1)
            extended_stats: Include extended latency statistics
            phase_detection: Enable automatic phase detection
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

        # Phase detection
        self._phase_detection_enabled = phase_detection
        self._phase_detector: Optional[PhaseDetector] = None

    def _build_command(self) -> List[str]:
        """Build the zpool iostat command."""
        cmd = ["zpool", "iostat", "-H", "-y"]  # -H for scripted mode (no headers), -y to skip first report (stats since boot)
        
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
                    # zpool iostat -l columns are interleaved read/write pairs:
                    #   total_wait(r,w) disk_wait(r,w) syncq_wait(r,w) asyncq_wait(r,w) scrub trim [rebuild]
                    total_wait_read=parts[7],
                    total_wait_write=parts[8],
                    disk_wait_read=parts[9],
                    disk_wait_write=parts[10],
                    syncq_wait_read=parts[11],
                    syncq_wait_write=parts[12],
                    asyncq_wait_read=parts[13],
                    asyncq_wait_write=parts[14],
                    scrub_wait=parts[15] if len(parts) > 15 else "-",
                    trim_wait=parts[16] if len(parts) > 16 else "-",
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
                    trim_wait="-",
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
                universal_newlines=True,
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

                        # Phase detection
                        if self._phase_detection_enabled and self._phase_detector:
                            total_iops = sample.operations_read + sample.operations_write
                            phase = self._phase_detector.push(total_iops, sample.timestamp)
                            sample.phase = phase.value
                            sample.segment_label = self._phase_detector._segment_label

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

        # Initialize phase detector
        if self._phase_detection_enabled:
            self._phase_detector = PhaseDetector()

        start_time = time.time()
        self.telemetry = ZpoolIostatTelemetry(
            pool_name=self.pool_name,
            start_time=start_time,
            start_time_iso=datetime.fromtimestamp(start_time).isoformat(),
            warmup_iterations=warmup_iterations,
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

    def signal_segment_change(self, label: str):
        """
        Signal a workload segment change (e.g. new thread count or write→read transition).

        This helps the phase detector label spans and expect a transition period.

        Args:
            label: Human-readable label like "8T-write", "16T-read", etc.
        """
        if self._phase_detector:
            self._phase_detector.set_segment_label(label)
            print_info(f"Zpool iostat collector: segment → {label}")

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

        # Finalize phase detection
        if self._phase_detector and self.telemetry:
            self.telemetry.phase_spans = self._phase_detector.finalize()

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


# ═══════════════════════════════════════════════════════════════════════════
# Statistics Helpers
# ═══════════════════════════════════════════════════════════════════════════

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
        "cv_percent": cv_percent,
    }


def _parse_bandwidth_mbps(bw_str: str) -> float:
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


def _parse_latency_ms(lat_str: str) -> float:
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


def _stats_for_samples(
    samples: List[ZpoolIostatSample],
) -> dict:
    """Compute IOPS/BW/latency stats for a list of samples."""
    if not samples:
        return {}

    read_ops = [s.operations_read for s in samples]
    write_ops = [s.operations_write for s in samples]
    total_ops = [r + w for r, w in zip(read_ops, write_ops)]
    read_bw = [_parse_bandwidth_mbps(s.bandwidth_read) for s in samples]
    write_bw = [_parse_bandwidth_mbps(s.bandwidth_write) for s in samples]

    # Active-only (at least some I/O)
    active = [(r, w, rb, wb) for r, w, rb, wb in zip(read_ops, write_ops, read_bw, write_bw) if r > 0 or w > 0]
    active_read_ops = [a[0] for a in active] if active else []
    active_write_ops = [a[1] for a in active] if active else []
    active_read_bw = [a[2] for a in active] if active else []
    active_write_bw = [a[3] for a in active] if active else []

    total_wait_read = [_parse_latency_ms(s.total_wait_read) for s in samples if _parse_latency_ms(s.total_wait_read) > 0]
    total_wait_write = [_parse_latency_ms(s.total_wait_write) for s in samples if _parse_latency_ms(s.total_wait_write) > 0]
    disk_wait_read = [_parse_latency_ms(s.disk_wait_read) for s in samples if _parse_latency_ms(s.disk_wait_read) > 0]
    disk_wait_write = [_parse_latency_ms(s.disk_wait_write) for s in samples if _parse_latency_ms(s.disk_wait_write) > 0]

    return {
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
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Summary Calculation
# ═══════════════════════════════════════════════════════════════════════════

def calculate_zpool_iostat_summary(telemetry: ZpoolIostatTelemetry) -> dict:
    """
    Calculate comprehensive summary statistics from zpool iostat telemetry data.

    Returns a dictionary with:
    - ``all_samples``: stats over every sample (original behaviour)
    - ``steady_state``: stats restricted to STEADY_STATE samples only
    - ``phase_detection``: phase breakdown, durations, etc.

    The steady-state view should have dramatically lower CV% because it
    excludes idle, warmup, cooldown, and transition periods.
    """
    if not telemetry or not telemetry.samples:
        return {}

    samples = telemetry.samples

    # Full stats (backward compatible)
    all_stats = _stats_for_samples(samples)

    # Steady-state stats
    ss_samples = telemetry.get_steady_state_samples()
    ss_stats = _stats_for_samples(ss_samples) if ss_samples else {}

    # Per-segment steady-state breakdown
    segment_stats = {}
    if ss_samples:
        seg_buckets: Dict[str, List[ZpoolIostatSample]] = {}
        for s in ss_samples:
            lbl = s.segment_label or "unknown"
            seg_buckets.setdefault(lbl, []).append(s)
        for lbl, seg_samples in seg_buckets.items():
            segment_stats[lbl] = {
                "sample_count": len(seg_samples),
                **_stats_for_samples(seg_samples),
            }

    # Fallback: if phase detection didn't run (e.g. reconstructed from JSON)
    # but segment labels exist, build per-segment stats from all labeled samples
    if not segment_stats:
        labeled = [s for s in samples if s.segment_label]
        if labeled:
            seg_buckets: Dict[str, List[ZpoolIostatSample]] = {}
            for s in labeled:
                seg_buckets.setdefault(s.segment_label, []).append(s)
            for lbl, seg_samples in seg_buckets.items():
                segment_stats[lbl] = {
                    "sample_count": len(seg_samples),
                    **_stats_for_samples(seg_samples),
                }

    # Phase summary
    phase_summary = _build_phase_summary(telemetry.phase_spans, samples)

    summary = {
        "pool_name": telemetry.pool_name,
        "total_samples": len(samples),
        "steady_state_samples": len(ss_samples),
        "duration_seconds": round(telemetry.end_time - telemetry.start_time, 2) if telemetry.end_time else None,
        # Backward-compatible top-level keys (all-samples view)
        **all_stats,
        # New phase-aware views
        "all_samples": all_stats,
        "steady_state": ss_stats,
        "per_segment_steady_state": segment_stats,
        "phase_detection": phase_summary,
    }

    return summary


# ═══════════════════════════════════════════════════════════════════════════
# Post-hoc Phase Detection (for pre-existing telemetry data)
# ═══════════════════════════════════════════════════════════════════════════

def run_phase_detection_posthoc(
    telemetry: ZpoolIostatTelemetry,
    *,
    idle_threshold: float = 500,
    active_threshold: float = 5000,
    steady_cv_max: float = 50.0,
    window_size: int = 3,
    min_hold_samples: int = 2,
) -> ZpoolIostatTelemetry:
    """
    Run phase detection on already-collected telemetry data.

    This is useful for:
    - Re-analysing saved JSON results with different thresholds
    - Processing data that was collected before phase detection existed

    Modifies the telemetry object *in-place* and returns it for convenience.
    """
    detector = PhaseDetector(
        idle_threshold=idle_threshold,
        active_threshold=active_threshold,
        steady_cv_max=steady_cv_max,
        window_size=window_size,
        min_hold_samples=min_hold_samples,
    )

    for sample in telemetry.samples:
        total_iops = sample.operations_read + sample.operations_write
        phase = detector.push(total_iops, sample.timestamp)
        sample.phase = phase.value

    telemetry.phase_spans = detector.finalize()
    return telemetry
