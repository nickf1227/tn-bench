"""
ARC Statistics Collector for tn-bench.

Collects ZFS ARC (Adaptive Replacement Cache) telemetry during pool benchmarks.
Runs in a background thread alongside the zpool iostat collector, capturing
cache performance metrics — particularly useful during READ phases.

Metrics collected:
  Core:     hit%, miss%, ARC size, reads/hits/misses per second
  Demand:   dh%, dm% (demand hit/miss percentages)
  Prefetch: ph%, pm% (prefetch hit/miss percentages)
  MRU/MFU:  mfusz%, mrusz%, mfu, mru (cache list sizes)
  L2ARC:    l2hit%, l2size, l2bytes (L2 hit rate, size, throughput)
  ZFetch:   zhits, zmisses, zissued, zahead (prefetch engine stats)

Reporting focuses on Core + L2ARC metrics; all fields are collected and
stored for advanced analysis.
"""

import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# Try importing project utils; fall back to no-ops for standalone testing
# ---------------------------------------------------------------------------
try:
    from utils import print_info, print_success, print_error, print_warning
except ImportError:
    def print_info(msg): print(f"[INFO] {msg}")
    def print_success(msg): print(f"[OK]   {msg}")
    def print_error(msg): print(f"[ERR]  {msg}")
    def print_warning(msg): print(f"[WARN] {msg}")


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

# Fields requested from arcstat (order matters — matches output columns)
ARCSTAT_FIELDS = [
    "hit%", "miss%", "arcsz", "read", "hits", "miss",
    "dh%", "dm%", "ph%", "pm%",
    "mfusz%", "mrusz%", "mfu", "mru",
    "l2hit%", "l2size", "l2bytes",
    "zhits", "zmisses", "zissued", "zahead",
]

ARCSTAT_FIELD_STRING = ",".join(ARCSTAT_FIELDS)


# ═══════════════════════════════════════════════════════════════════════════
# Unit Conversion
# ═══════════════════════════════════════════════════════════════════════════

def _bytes_to_gib(value: float) -> float:
    """Convert bytes to GiB."""
    return round(value / (1024 ** 3), 3)


def _bytes_to_mbs(value: float) -> float:
    """Convert bytes/sec to MB/s."""
    return round(value / (1024 ** 2), 2)


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ArcstatSample:
    """A single sample of arcstat data."""
    timestamp: float
    timestamp_iso: str
    # Core metrics
    arc_hit_pct: float          # hit%
    arc_miss_pct: float         # miss%
    arc_size_gib: float         # arcsz (converted to GiB)
    reads_per_sec: float        # read
    hits_per_sec: float         # hits
    misses_per_sec: float       # miss
    # Demand metrics
    demand_hit_pct: float       # dh%
    demand_miss_pct: float      # dm%
    # Prefetch metrics
    prefetch_hit_pct: float     # ph%
    prefetch_miss_pct: float    # pm%
    # MRU/MFU metrics
    mfu_size_pct: float         # mfusz%
    mru_size_pct: float         # mrusz%
    mfu_hits_per_sec: float     # mfu
    mru_hits_per_sec: float     # mru
    # L2ARC metrics
    l2_hit_pct: float           # l2hit%
    l2_size_gib: float          # l2size (converted to GiB)
    l2_bytes_per_sec_mbs: float # l2bytes (converted to MB/s)
    # ZFetch (prefetch engine) metrics
    zfetch_hits_per_sec: float  # zhits
    zfetch_misses_per_sec: float  # zmisses
    zfetch_issued_per_sec: float  # zissued
    zfetch_ahead_per_sec: float   # zahead
    # Phase tagging (set by collector from benchmark harness signals)
    segment_label: str = ""


@dataclass
class ArcstatTelemetry:
    """Complete arcstat telemetry data for a benchmark run."""
    start_time: float
    start_time_iso: str
    end_time: Optional[float] = None
    end_time_iso: Optional[str] = None
    warmup_iterations: int = 0
    cooldown_iterations: int = 0
    samples: List[ArcstatSample] = field(default_factory=list)

    def to_dict(self, sample_interval: int = 1) -> dict:
        """
        Convert telemetry to dictionary for JSON serialization.

        Args:
            sample_interval: Keep every Nth sample (default: 1 = all samples).
                           Use 5 to keep every 5th sample for output size.
        """
        downsampled = self.samples[::sample_interval] if sample_interval > 1 else self.samples

        return {
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
            "samples": [asdict(s) for s in downsampled],
        }

    def get_read_phase_samples(self) -> List[ArcstatSample]:
        """Return only samples from READ phase segments."""
        return [s for s in self.samples if s.segment_label.endswith("-read")]

    def get_samples_by_segment(self, label: str) -> List[ArcstatSample]:
        """Return samples matching a specific segment label."""
        return [s for s in self.samples if s.segment_label == label]


# ═══════════════════════════════════════════════════════════════════════════
# Collector
# ═══════════════════════════════════════════════════════════════════════════

class ArcstatCollector:
    """
    Background collector for ZFS ARC statistics.

    Lifecycle mirrors ZpoolIostatCollector:
        collector = ArcstatCollector(interval=1)
        collector.start(warmup_iterations=3)
        collector.signal_segment_change("8T-read")
        ...
        telemetry = collector.stop(cooldown_iterations=3)
    """

    def __init__(self, interval: int = 1):
        """
        Initialize the arcstat collector.

        Args:
            interval: Sampling interval in seconds (default: 1)
        """
        self.interval = interval
        self.telemetry: Optional[ArcstatTelemetry] = None
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._warmup_count = 0
        self._warmup_target = 0
        self._segment_label: str = ""

    def _build_command(self) -> List[str]:
        """Build the arcstat command."""
        # -p for parseable (raw numbers, no unit suffixes)
        # -f to select fields
        # interval count=0 means run forever (we'll kill it on stop)
        return [
            "arcstat", "-p",
            "-f", ARCSTAT_FIELD_STRING,
            str(self.interval),
        ]

    def _parse_line(self, line: str) -> Optional[ArcstatSample]:
        """
        Parse a single line of arcstat -p output.

        arcstat -p outputs tab/space-separated numeric values in the order
        of the requested fields, with a header line at the start.
        """
        parts = line.strip().split()
        if len(parts) < len(ARCSTAT_FIELDS):
            return None

        try:
            timestamp = time.time()
            # Map positional fields
            vals = [float(p) for p in parts[:len(ARCSTAT_FIELDS)]]

            return ArcstatSample(
                timestamp=timestamp,
                timestamp_iso=datetime.fromtimestamp(timestamp).isoformat(),
                # Core
                arc_hit_pct=vals[0],
                arc_miss_pct=vals[1],
                arc_size_gib=_bytes_to_gib(vals[2]),
                reads_per_sec=vals[3],
                hits_per_sec=vals[4],
                misses_per_sec=vals[5],
                # Demand
                demand_hit_pct=vals[6],
                demand_miss_pct=vals[7],
                # Prefetch
                prefetch_hit_pct=vals[8],
                prefetch_miss_pct=vals[9],
                # MRU/MFU
                mfu_size_pct=vals[10],
                mru_size_pct=vals[11],
                mfu_hits_per_sec=vals[12],
                mru_hits_per_sec=vals[13],
                # L2ARC
                l2_hit_pct=vals[14],
                l2_size_gib=_bytes_to_gib(vals[15]),
                l2_bytes_per_sec_mbs=_bytes_to_mbs(vals[16]),
                # ZFetch
                zfetch_hits_per_sec=vals[17],
                zfetch_misses_per_sec=vals[18],
                zfetch_issued_per_sec=vals[19],
                zfetch_ahead_per_sec=vals[20],
                # Phase
                segment_label=self._segment_label,
            )
        except (ValueError, IndexError) as e:
            print_warning(f"Failed to parse arcstat line: {line.strip()} - {e}")
            return None

    def _collection_loop(self):
        """Main collection loop running in background thread."""
        cmd = self._build_command()
        print_info(f"Starting arcstat collection (interval: {self.interval}s, fields: {len(ARCSTAT_FIELDS)})")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            header_skipped = False

            while not self._stop_event.is_set() and self._process.poll() is None:
                try:
                    line = self._process.stdout.readline()
                    if not line:
                        time.sleep(0.1)
                        continue

                    line = line.strip()
                    if not line:
                        continue

                    # Skip the header line (field names)
                    if not header_skipped:
                        # Header contains field names like "hit%" — skip it
                        if any(f in line for f in ["hit%", "miss%", "arcsz"]):
                            header_skipped = True
                            continue
                        # If it doesn't look like a header, try parsing anyway
                        # (some arcstat versions may not print a header with -p)

                    sample = self._parse_line(line)
                    if sample and self.telemetry:
                        # Track warmup
                        if self._warmup_count < self._warmup_target:
                            self._warmup_count += 1

                        self.telemetry.samples.append(sample)

                except Exception as e:
                    if not self._stop_event.is_set():
                        print_warning(f"Error reading arcstat output: {e}")

        except Exception as e:
            if not self._stop_event.is_set():
                print_error(f"Arcstat collection error: {e}")
        finally:
            self._cleanup_process()

    def _cleanup_process(self):
        """Clean up the subprocess."""
        if self._process:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            except Exception:
                pass
            finally:
                self._process = None

    def start(self, warmup_iterations: int = 3) -> bool:
        """
        Start the arcstat collector.

        Args:
            warmup_iterations: Number of samples to collect before benchmark starts

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            print_warning("Arcstat collector already running")
            return False

        self._warmup_target = warmup_iterations
        self._warmup_count = 0
        self._stop_event.clear()

        start_time = time.time()
        self.telemetry = ArcstatTelemetry(
            start_time=start_time,
            start_time_iso=datetime.fromtimestamp(start_time).isoformat(),
            warmup_iterations=warmup_iterations,
        )

        self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._thread.start()
        self._running = True

        # Wait for warmup if specified
        if warmup_iterations > 0:
            print_info(f"Warming up arcstat collector ({warmup_iterations} samples)...")
            while self._warmup_count < warmup_iterations:
                if not self._running or self._stop_event.is_set():
                    return False
                time.sleep(0.1)
            print_success("Arcstat collector warmup complete")

        return True

    def signal_segment_change(self, label: str):
        """
        Signal a workload segment change.

        Args:
            label: Human-readable label like "8T-write", "16T-read", etc.
        """
        self._segment_label = label
        print_info(f"Arcstat collector: segment → {label}")

    def stop(self, cooldown_iterations: int = 3) -> Optional[ArcstatTelemetry]:
        """
        Stop the arcstat collector.

        Args:
            cooldown_iterations: Number of samples to collect after benchmark ends

        Returns:
            ArcstatTelemetry object with all collected data
        """
        if not self._running:
            print_warning("Arcstat collector not running")
            return self.telemetry

        # Wait for cooldown
        if cooldown_iterations > 0 and self.telemetry:
            print_info(f"Cooling down arcstat collector ({cooldown_iterations} samples)...")
            current_count = len(self.telemetry.samples)
            target = current_count + cooldown_iterations
            while len(self.telemetry.samples) < target:
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)
            print_success("Arcstat collector cooldown complete")

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
            print_success(f"Arcstat collection complete: {len(self.telemetry.samples)} samples")

        return self.telemetry

    def is_running(self) -> bool:
        """Check if the collector is currently running."""
        return self._running and self._thread and self._thread.is_alive()

    def get_sample_count(self) -> int:
        """Get the current number of collected samples."""
        return len(self.telemetry.samples) if self.telemetry else 0


# ═══════════════════════════════════════════════════════════════════════════
# Statistics Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _calculate_stats(values: List[float]) -> dict:
    """Calculate comprehensive statistics for a list of values."""
    if not values:
        return {}

    n = len(values)
    sorted_vals = sorted(values)

    mean = sum(values) / n

    mid = n // 2
    median = sorted_vals[mid] if n % 2 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2

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

    variance = sum((x - mean) ** 2 for x in values) / n
    std_dev = variance ** 0.5
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


# ═══════════════════════════════════════════════════════════════════════════
# Summary Calculation
# ═══════════════════════════════════════════════════════════════════════════

def calculate_arcstat_summary(telemetry: ArcstatTelemetry) -> dict:
    """
    Calculate summary statistics from arcstat telemetry data.

    Focuses on READ-phase segments only for meaningful ARC analysis,
    since ARC hit rates during writes are not indicative of cache performance.

    Returns a dictionary with:
    - ``all_samples``: stats over every sample
    - ``read_phase``: stats restricted to READ-phase segments only
    - ``per_segment_read``: per-thread-count READ breakdown
    """
    if not telemetry or not telemetry.samples:
        return {}

    samples = telemetry.samples
    read_samples = telemetry.get_read_phase_samples()

    # All-samples stats (for reference)
    all_stats = _stats_for_arcstat_samples(samples)

    # Read-phase-only stats
    read_stats = _stats_for_arcstat_samples(read_samples) if read_samples else {}

    # Per-segment read breakdown
    segment_stats = {}
    if read_samples:
        seg_buckets: Dict[str, List[ArcstatSample]] = {}
        for s in read_samples:
            seg_buckets.setdefault(s.segment_label, []).append(s)
        for lbl, seg_samples in seg_buckets.items():
            segment_stats[lbl] = {
                "sample_count": len(seg_samples),
                **_stats_for_arcstat_samples(seg_samples),
            }

    return {
        "total_samples": len(samples),
        "read_phase_samples": len(read_samples),
        "duration_seconds": round(telemetry.end_time - telemetry.start_time, 2) if telemetry.end_time else None,
        "all_samples": all_stats,
        "read_phase": read_stats,
        "per_segment_read": segment_stats,
    }


def _stats_for_arcstat_samples(samples: List[ArcstatSample]) -> dict:
    """Compute ARC stats for a list of samples. Reports Core + L2ARC metrics."""
    if not samples:
        return {}

    return {
        "arc_hit_pct": _calculate_stats([s.arc_hit_pct for s in samples]),
        "arc_miss_pct": _calculate_stats([s.arc_miss_pct for s in samples]),
        "arc_size_gib": _calculate_stats([s.arc_size_gib for s in samples]),
        "reads_per_sec": _calculate_stats([s.reads_per_sec for s in samples]),
        "hits_per_sec": _calculate_stats([s.hits_per_sec for s in samples]),
        "misses_per_sec": _calculate_stats([s.misses_per_sec for s in samples]),
        "l2_hit_pct": _calculate_stats([s.l2_hit_pct for s in samples]),
        "l2_size_gib": _calculate_stats([s.l2_size_gib for s in samples]),
        "l2_bytes_per_sec_mbs": _calculate_stats([s.l2_bytes_per_sec_mbs for s in samples]),
    }
