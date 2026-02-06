"""
TN-Bench Analytics Module - Neutral Data Presentation
Part of TN-Bench 2.1

Includes:
  - ResultAnalyzer: scaling analysis (thread efficiency, deltas, etc.)
  - TelemetryAnalyzer: zpool iostat telemetry analysis (IOPS, bandwidth,
    latency, queue depths, phase detection, anomaly detection, I/O sizing)
"""

import json
import math
import statistics
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


# ══════════════════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════════════════

@dataclass
class Observation:
    """A neutral observation about benchmark behavior."""
    category: str
    description: str
    data: Optional[Dict[str, Any]] = None


@dataclass
class PoolAnalysis:
    """Analysis results for a single pool."""
    name: str
    write_scaling: Dict[str, Any]
    read_scaling: Dict[str, Any]
    observations: List[Observation] = field(default_factory=list)


@dataclass
class TelemetryStats:
    """Comprehensive statistics for a metric."""
    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    min: float = 0.0
    max: float = 0.0
    std_dev: float = 0.0
    p50: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    cv_percent: float = 0.0  # Coefficient of variation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "min": self.min,
            "max": self.max,
            "std_dev": self.std_dev,
            "p50": self.p50,
            "p90": self.p90,
            "p95": self.p95,
            "p99": self.p99,
            "cv_percent": self.cv_percent,
        }


class IOPhase(Enum):
    """I/O activity phase classification."""
    IDLE = "idle"
    WRITE = "write"
    READ = "read"
    MIXED = "mixed"


@dataclass
class PhaseSegment:
    """A detected phase segment in the telemetry timeline."""
    phase: IOPhase
    start_idx: int
    end_idx: int
    duration_samples: int
    start_time: str = ""
    end_time: str = ""
    stats: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "phase": self.phase.value,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "duration_samples": self.duration_samples,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }
        if self.stats:
            d["stats"] = self.stats
        return d


@dataclass
class Anomaly:
    """A detected statistical anomaly in telemetry data."""
    index: int
    timestamp: str
    metric: str
    value: float
    z_score: float
    direction: str  # "spike" or "drop"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "metric": self.metric,
            "value": round(self.value, 4),
            "z_score": round(self.z_score, 2),
            "direction": self.direction,
        }


@dataclass
class TelemetryPoolAnalysis:
    """Complete telemetry analysis for one pool."""
    pool_name: str
    sample_summary: Dict[str, Any] = field(default_factory=dict)
    iops: Dict[str, Any] = field(default_factory=dict)
    bandwidth_mbps: Dict[str, Any] = field(default_factory=dict)
    latency_ms: Dict[str, Any] = field(default_factory=dict)
    queue_depths: Dict[str, Any] = field(default_factory=dict)
    phases: List[PhaseSegment] = field(default_factory=list)
    phase_stats: List[Dict[str, Any]] = field(default_factory=list)
    anomalies: List[Anomaly] = field(default_factory=list)
    io_size_kb: Dict[str, Any] = field(default_factory=dict)
    capacity_gib: Dict[str, Any] = field(default_factory=dict)
    observations: List[Observation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pool_name": self.pool_name,
            "sample_summary": self.sample_summary,
            "iops": self.iops,
            "bandwidth_mbps": self.bandwidth_mbps,
            "latency_ms": self.latency_ms,
            "queue_depths": self.queue_depths,
            "phases": [p.to_dict() for p in self.phases],
            "phase_stats": self.phase_stats,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "anomaly_count": len(self.anomalies),
            "io_size_kb": self.io_size_kb,
            "capacity_gib": self.capacity_gib,
            "observations": [
                {"category": o.category, "description": o.description, "data": o.data}
                for o in self.observations
            ],
        }


@dataclass
class SystemAnalysis:
    """Complete system analysis results."""
    pool_analyses: List[PoolAnalysis] = field(default_factory=list)
    disk_comparison: Dict[str, Any] = field(default_factory=dict)
    telemetry_analyses: List[TelemetryPoolAnalysis] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pool_analyses": [
                {
                    "name": pa.name,
                    "write_scaling": pa.write_scaling,
                    "read_scaling": pa.read_scaling,
                    "observations": [
                        {"category": o.category, "description": o.description, "data": o.data}
                        for o in pa.observations
                    ]
                }
                for pa in self.pool_analyses
            ],
            "disk_comparison": self.disk_comparison,
            "telemetry_analyses": [ta.to_dict() for ta in self.telemetry_analyses],
        }


# ══════════════════════════════════════════════════════════════
# Unit Parsers
# ══════════════════════════════════════════════════════════════

def parse_bandwidth(val) -> float:
    """Parse bandwidth value to bytes/sec.

    Accepts:
      - String with suffix: '641M', '8.96M', '1.23G', '0', '-'
      - Numeric (int/float): returned as-is (assumed bytes)
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip()
    if not val or val == '-' or val == '0':
        return 0.0
    multipliers = {
        'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4,
        'k': 1024, 'm': 1024**2, 'g': 1024**3, 't': 1024**4,
    }
    for suffix, mult in multipliers.items():
        if val.endswith(suffix):
            try:
                return float(val[:-1]) * mult
            except ValueError:
                return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def parse_latency_to_ms(val) -> Optional[float]:
    """Parse latency value to milliseconds.

    Accepts:
      - String with suffix: '130ms', '1us', '2ns', '-'
      - Numeric (int/float): returned as-is (assumed microseconds for
        backward compat with simplified schema where values are in µs)
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        # Simplified schema stores latency as microseconds
        return float(val) / 1000.0
    val = str(val).strip()
    if not val or val == '-':
        return None
    conversions = {
        'ns': 1e-6, 'us': 1e-3, 'ms': 1.0, 's': 1000.0,
    }
    for suffix, mult in conversions.items():
        if val.endswith(suffix):
            try:
                return float(val[:-len(suffix)]) * mult
            except ValueError:
                return None
    try:
        return float(val)
    except ValueError:
        return None


def parse_capacity(val) -> float:
    """Parse capacity string to GiB."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val) / (1024**3)  # Assume bytes
    val = str(val).strip()
    if not val or val == '-':
        return 0.0
    multipliers = {'K': 1/1024/1024, 'M': 1/1024, 'G': 1.0, 'T': 1024.0}
    for suffix, mult in multipliers.items():
        if val.endswith(suffix):
            try:
                return float(val[:-1]) * mult
            except ValueError:
                return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


# ══════════════════════════════════════════════════════════════
# Statistics
# ══════════════════════════════════════════════════════════════

def compute_stats(values: List[float]) -> TelemetryStats:
    """Compute comprehensive statistics for a numeric series."""
    if not values:
        return TelemetryStats()

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mean_val = statistics.mean(values)
    std_val = statistics.stdev(values) if n > 1 else 0.0

    def percentile(p: float) -> float:
        idx = min(int(n * p), n - 1)
        return sorted_vals[idx]

    cv = (std_val / mean_val * 100.0) if mean_val > 0 else 0.0

    return TelemetryStats(
        count=n,
        mean=round(mean_val, 4),
        median=round(statistics.median(values), 4),
        min=round(sorted_vals[0], 4),
        max=round(sorted_vals[-1], 4),
        std_dev=round(std_val, 4),
        p50=round(percentile(0.50), 4),
        p90=round(percentile(0.90), 4),
        p95=round(percentile(0.95), 4),
        p99=round(percentile(0.99), 4),
        cv_percent=round(cv, 2),
    )


# ══════════════════════════════════════════════════════════════
# Telemetry Analyzer
# ══════════════════════════════════════════════════════════════

class TelemetryAnalyzer:
    """Analyzes zpool iostat telemetry data.

    Handles both the native TN-Bench telemetry format (string-encoded
    bandwidth/latency with unit suffixes from ZpoolIostatCollector) and
    a simplified numeric format.

    Native sample fields:
        operations_read, operations_write, bandwidth_read, bandwidth_write,
        total_wait_read, total_wait_write, disk_wait_read, disk_wait_write,
        syncq_wait_read, syncq_wait_write, asyncq_wait_read, asyncq_wait_write,
        capacity_used, capacity_avail, timestamp_iso

    Simplified sample fields (also accepted):
        read_ops, write_ops, read_bytes, write_bytes,
        read_wait, write_wait, total_wait,
        asyncq_wait, syncq_wait, timestamp
    """

    # Z-score threshold for anomaly detection
    ANOMALY_THRESHOLD = 3.0
    # Minimum samples in a phase before we report stats
    MIN_PHASE_SAMPLES = 3
    # Short idle gap that gets merged between same-type phases
    MAX_IDLE_GAP_SAMPLES = 3

    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.pool_analyses: List[TelemetryPoolAnalysis] = []

    def analyze(self) -> List[TelemetryPoolAnalysis]:
        """Analyze all pools in the results data."""
        for pool in self.results.get("pools", []):
            analysis = self._analyze_pool(pool)
            if analysis:
                self.pool_analyses.append(analysis)
        return self.pool_analyses

    # ── Sample Normalization ──────────────────────────────────

    @staticmethod
    def _normalize_sample(s: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a sample to canonical field names.

        Returns a dict with:
          write_ops (float), read_ops (float),
          write_bytes (float), read_bytes (float),  # bytes/sec
          total_wait_read_ms, total_wait_write_ms,
          disk_wait_read_ms, disk_wait_write_ms,
          asyncq_wait_read_ms, asyncq_wait_write_ms,
          syncq_wait_read_ms, syncq_wait_write_ms,
          capacity_used_gib (float),
          timestamp_iso (str)
        """
        n = {}

        # IOPS
        n["write_ops"] = float(s.get("operations_write") or s.get("write_ops") or 0)
        n["read_ops"] = float(s.get("operations_read") or s.get("read_ops") or 0)
        n["total_ops"] = n["write_ops"] + n["read_ops"]

        # Bandwidth → bytes/sec
        if "bandwidth_write" in s:
            n["write_bytes"] = parse_bandwidth(s["bandwidth_write"])
        else:
            n["write_bytes"] = float(s.get("write_bytes", 0) or 0)

        if "bandwidth_read" in s:
            n["read_bytes"] = parse_bandwidth(s["bandwidth_read"])
        else:
            n["read_bytes"] = float(s.get("read_bytes", 0) or 0)

        # Latencies → ms
        # Total wait
        if "total_wait_read" in s:
            n["total_wait_read_ms"] = parse_latency_to_ms(s["total_wait_read"])
        elif "read_wait" in s:
            n["total_wait_read_ms"] = parse_latency_to_ms(s["read_wait"])
        else:
            n["total_wait_read_ms"] = None

        if "total_wait_write" in s:
            n["total_wait_write_ms"] = parse_latency_to_ms(s["total_wait_write"])
        elif "write_wait" in s:
            n["total_wait_write_ms"] = parse_latency_to_ms(s["write_wait"])
        else:
            n["total_wait_write_ms"] = None

        if "total_wait" in s and n["total_wait_read_ms"] is None:
            # Simplified schema: single total_wait field
            tw = parse_latency_to_ms(s["total_wait"])
            n["total_wait_read_ms"] = tw
            n["total_wait_write_ms"] = tw

        # Disk wait
        n["disk_wait_read_ms"] = parse_latency_to_ms(s.get("disk_wait_read"))
        n["disk_wait_write_ms"] = parse_latency_to_ms(s.get("disk_wait_write"))

        # Queue waits
        n["asyncq_wait_read_ms"] = parse_latency_to_ms(s.get("asyncq_wait_read"))
        n["asyncq_wait_write_ms"] = parse_latency_to_ms(
            s.get("asyncq_wait_write") or s.get("asyncq_wait")
        )
        n["syncq_wait_read_ms"] = parse_latency_to_ms(s.get("syncq_wait_read"))
        n["syncq_wait_write_ms"] = parse_latency_to_ms(
            s.get("syncq_wait_write") or s.get("syncq_wait")
        )

        # Capacity
        n["capacity_used_gib"] = parse_capacity(s.get("capacity_used", 0))

        # Timestamp
        n["timestamp_iso"] = s.get("timestamp_iso") or s.get("timestamp", "")
        if isinstance(n["timestamp_iso"], (int, float)):
            n["timestamp_iso"] = ""  # epoch timestamp, not ISO

        return n

    # ── Pool Analysis ─────────────────────────────────────────

    def _analyze_pool(self, pool: Dict[str, Any]) -> Optional[TelemetryPoolAnalysis]:
        """Analyze telemetry for a single pool."""
        name = pool.get("name", "unknown")

        # Find telemetry data (support both key names)
        telemetry = pool.get("zpool_iostat_telemetry") or pool.get("telemetry") or {}
        raw_samples = telemetry.get("samples", [])

        if not raw_samples:
            return None

        # Normalize all samples
        samples = [self._normalize_sample(s) for s in raw_samples]

        analysis = TelemetryPoolAnalysis(pool_name=name)

        # ── Sample summary ──
        analysis.sample_summary = self._compute_sample_summary(samples)

        # ── Separate active vs idle ──
        active_write = [s for s in samples if s["write_ops"] > 0]
        active_read = [s for s in samples if s["read_ops"] > 0]

        # ── IOPS statistics ──
        analysis.iops = self._compute_iops_stats(samples, active_write, active_read)

        # ── Bandwidth statistics (MB/s) ──
        analysis.bandwidth_mbps = self._compute_bandwidth_stats(
            samples, active_write, active_read
        )

        # ── Latency statistics (ms) ──
        analysis.latency_ms = self._compute_latency_stats(
            samples, active_write, active_read
        )

        # ── Queue depth statistics ──
        analysis.queue_depths = self._compute_queue_stats(
            samples, active_write, active_read
        )

        # ── Phase detection ──
        analysis.phases = self._detect_phases(samples)
        analysis.phase_stats = self._compute_phase_stats(analysis.phases, samples)

        # ── Anomaly detection ──
        analysis.anomalies = self._detect_anomalies(active_write, active_read)

        # ── I/O size analysis ──
        analysis.io_size_kb = self._compute_io_sizes(active_write, active_read)

        # ── Capacity tracking ──
        cap_values = [s["capacity_used_gib"] for s in samples]
        if cap_values:
            analysis.capacity_gib = {
                "start": round(cap_values[0], 2),
                "end": round(cap_values[-1], 2),
                "max": round(max(cap_values), 2),
                "min": round(min(cap_values), 2),
            }

        # ── Derived observations ──
        analysis.observations = self._generate_observations(analysis)

        return analysis

    # ── Sample Summary ────────────────────────────────────────

    def _compute_sample_summary(self, samples: List[Dict]) -> Dict[str, Any]:
        n_total = len(samples)
        active_write_indices = {i for i, s in enumerate(samples) if s["write_ops"] > 0}
        active_read_indices = {i for i, s in enumerate(samples) if s["read_ops"] > 0}
        active_any = active_write_indices | active_read_indices
        n_idle = n_total - len(active_any)

        return {
            "total_samples": n_total,
            "active_write_samples": len(active_write_indices),
            "active_read_samples": len(active_read_indices),
            "idle_samples": n_idle,
            "active_write_pct": round(len(active_write_indices) / n_total * 100, 1)
            if n_total
            else 0,
            "active_read_pct": round(len(active_read_indices) / n_total * 100, 1)
            if n_total
            else 0,
            "idle_pct": round(n_idle / n_total * 100, 1) if n_total else 0,
        }

    # ── IOPS ──────────────────────────────────────────────────

    def _compute_iops_stats(
        self,
        all_samples: List[Dict],
        active_write: List[Dict],
        active_read: List[Dict],
    ) -> Dict[str, Any]:
        return {
            "all_samples": {
                "write_ops": compute_stats(
                    [s["write_ops"] for s in all_samples]
                ).to_dict(),
                "read_ops": compute_stats(
                    [s["read_ops"] for s in all_samples]
                ).to_dict(),
                "total_ops": compute_stats(
                    [s["total_ops"] for s in all_samples]
                ).to_dict(),
            },
            "active_only": {
                "write_ops": compute_stats(
                    [s["write_ops"] for s in active_write]
                ).to_dict(),
                "read_ops": compute_stats(
                    [s["read_ops"] for s in active_read]
                ).to_dict(),
            },
        }

    # ── Bandwidth ─────────────────────────────────────────────

    def _compute_bandwidth_stats(
        self,
        all_samples: List[Dict],
        active_write: List[Dict],
        active_read: List[Dict],
    ) -> Dict[str, Any]:
        MB = 1024**2

        return {
            "all_samples": {
                "write": compute_stats(
                    [s["write_bytes"] / MB for s in all_samples]
                ).to_dict(),
                "read": compute_stats(
                    [s["read_bytes"] / MB for s in all_samples]
                ).to_dict(),
            },
            "active_only": {
                "write": compute_stats(
                    [s["write_bytes"] / MB for s in active_write]
                ).to_dict(),
                "read": compute_stats(
                    [s["read_bytes"] / MB for s in active_read]
                ).to_dict(),
            },
        }

    # ── Latency ───────────────────────────────────────────────

    def _compute_latency_stats(
        self,
        all_samples: List[Dict],
        active_write: List[Dict],
        active_read: List[Dict],
    ) -> Dict[str, Any]:
        def _collect(samples, key):
            return [s[key] for s in samples if s[key] is not None]

        return {
            "total_wait": {
                "read": compute_stats(
                    _collect(all_samples, "total_wait_read_ms")
                ).to_dict(),
                "write": compute_stats(
                    _collect(all_samples, "total_wait_write_ms")
                ).to_dict(),
            },
            "disk_wait": {
                "read": compute_stats(
                    _collect(all_samples, "disk_wait_read_ms")
                ).to_dict(),
                "write": compute_stats(
                    _collect(all_samples, "disk_wait_write_ms")
                ).to_dict(),
            },
            "active_only": {
                "total_wait_write": compute_stats(
                    _collect(active_write, "total_wait_write_ms")
                ).to_dict(),
                "total_wait_read": compute_stats(
                    _collect(active_read, "total_wait_read_ms")
                ).to_dict(),
                "disk_wait_read": compute_stats(
                    _collect(active_read, "disk_wait_read_ms")
                ).to_dict(),
                "disk_wait_write": compute_stats(
                    _collect(active_write, "disk_wait_write_ms")
                ).to_dict(),
            },
        }

    # ── Queue Depths ──────────────────────────────────────────

    def _compute_queue_stats(
        self,
        all_samples: List[Dict],
        active_write: List[Dict],
        active_read: List[Dict],
    ) -> Dict[str, Any]:
        def _collect(samples, key):
            return [s[key] for s in samples if s[key] is not None]

        return {
            "asyncq_wait_write": compute_stats(
                _collect(all_samples, "asyncq_wait_write_ms")
            ).to_dict(),
            "asyncq_wait_read": compute_stats(
                _collect(all_samples, "asyncq_wait_read_ms")
            ).to_dict(),
            "syncq_wait_write": compute_stats(
                _collect(all_samples, "syncq_wait_write_ms")
            ).to_dict(),
            "syncq_wait_read": compute_stats(
                _collect(all_samples, "syncq_wait_read_ms")
            ).to_dict(),
            "active_only": {
                "asyncq_wait_write": compute_stats(
                    _collect(active_write, "asyncq_wait_write_ms")
                ).to_dict(),
                "syncq_wait_write": compute_stats(
                    _collect(active_write, "syncq_wait_write_ms")
                ).to_dict(),
            },
        }

    # ── Phase Detection ───────────────────────────────────────

    def _classify_sample(self, s: Dict) -> IOPhase:
        """Classify a single sample into an I/O phase."""
        has_write = s["write_ops"] > 0
        has_read = s["read_ops"] > 0
        if has_write and has_read:
            return IOPhase.MIXED
        elif has_write:
            return IOPhase.WRITE
        elif has_read:
            return IOPhase.READ
        else:
            return IOPhase.IDLE

    def _detect_phases(self, samples: List[Dict]) -> List[PhaseSegment]:
        """Detect I/O phases from the telemetry timeline.

        Merges short idle gaps (<= MAX_IDLE_GAP_SAMPLES) between segments
        of the same activity type.
        """
        if not samples:
            return []

        # Initial per-sample classification
        raw_segments: List[PhaseSegment] = []
        current_phase = self._classify_sample(samples[0])
        phase_start = 0

        for i in range(1, len(samples)):
            phase = self._classify_sample(samples[i])
            if phase != current_phase:
                raw_segments.append(PhaseSegment(
                    phase=current_phase,
                    start_idx=phase_start,
                    end_idx=i - 1,
                    duration_samples=i - phase_start,
                    start_time=samples[phase_start]["timestamp_iso"],
                    end_time=samples[i - 1]["timestamp_iso"],
                ))
                current_phase = phase
                phase_start = i

        # Close final segment
        raw_segments.append(PhaseSegment(
            phase=current_phase,
            start_idx=phase_start,
            end_idx=len(samples) - 1,
            duration_samples=len(samples) - phase_start,
            start_time=samples[phase_start]["timestamp_iso"],
            end_time=samples[-1]["timestamp_iso"],
        ))

        # Merge consecutive same-phase segments
        merged: List[PhaseSegment] = []
        for seg in raw_segments:
            if merged and seg.phase == merged[-1].phase:
                merged[-1].end_idx = seg.end_idx
                merged[-1].duration_samples = seg.end_idx - merged[-1].start_idx + 1
                merged[-1].end_time = seg.end_time
            else:
                merged.append(PhaseSegment(
                    phase=seg.phase,
                    start_idx=seg.start_idx,
                    end_idx=seg.end_idx,
                    duration_samples=seg.duration_samples,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                ))

        # Consolidate: bridge short idle gaps between same activity type
        consolidated: List[PhaseSegment] = []
        i = 0
        while i < len(merged):
            current = PhaseSegment(
                phase=merged[i].phase,
                start_idx=merged[i].start_idx,
                end_idx=merged[i].end_idx,
                duration_samples=merged[i].duration_samples,
                start_time=merged[i].start_time,
                end_time=merged[i].end_time,
            )
            while (
                i + 2 < len(merged)
                and merged[i + 1].phase == IOPhase.IDLE
                and merged[i + 1].duration_samples <= self.MAX_IDLE_GAP_SAMPLES
                and merged[i + 2].phase == current.phase
            ):
                current.end_idx = merged[i + 2].end_idx
                current.duration_samples = current.end_idx - current.start_idx + 1
                current.end_time = merged[i + 2].end_time
                i += 2
            consolidated.append(current)
            i += 1

        return consolidated

    def _compute_phase_stats(
        self, phases: List[PhaseSegment], samples: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Compute per-phase statistics."""
        MB = 1024**2
        results = []

        for phase in phases:
            ps: Dict[str, Any] = {
                "phase": phase.phase.value,
                "duration_samples": phase.duration_samples,
                "start_time": phase.start_time,
                "end_time": phase.end_time,
            }

            if phase.phase == IOPhase.IDLE:
                results.append(ps)
                continue

            start = phase.start_idx
            end = phase.end_idx + 1
            phase_samples = samples[start:end]

            if len(phase_samples) < self.MIN_PHASE_SAMPLES:
                results.append(ps)
                continue

            # Collect non-zero values for the active operation(s)
            nz_w_ops = [s["write_ops"] for s in phase_samples if s["write_ops"] > 0]
            nz_r_ops = [s["read_ops"] for s in phase_samples if s["read_ops"] > 0]
            nz_w_bw = [s["write_bytes"] / MB for s in phase_samples if s["write_bytes"] > 0]
            nz_r_bw = [s["read_bytes"] / MB for s in phase_samples if s["read_bytes"] > 0]

            if nz_w_ops:
                ps["write_iops"] = compute_stats(nz_w_ops).to_dict()
                ps["write_bandwidth_mbps"] = compute_stats(nz_w_bw).to_dict()

                # Latency during this phase
                w_lat = [
                    s["total_wait_write_ms"]
                    for s in phase_samples
                    if s["write_ops"] > 0 and s["total_wait_write_ms"] is not None
                ]
                if w_lat:
                    ps["write_latency_ms"] = compute_stats(w_lat).to_dict()

            if nz_r_ops:
                ps["read_iops"] = compute_stats(nz_r_ops).to_dict()
                ps["read_bandwidth_mbps"] = compute_stats(nz_r_bw).to_dict()

                r_lat = [
                    s["total_wait_read_ms"]
                    for s in phase_samples
                    if s["read_ops"] > 0 and s["total_wait_read_ms"] is not None
                ]
                if r_lat:
                    ps["read_latency_ms"] = compute_stats(r_lat).to_dict()

            results.append(ps)

        return results

    # ── Anomaly Detection ─────────────────────────────────────

    def _detect_anomalies(
        self, active_write: List[Dict], active_read: List[Dict]
    ) -> List[Anomaly]:
        """Detect statistical anomalies (z-score > threshold) in active samples."""
        anomalies: List[Anomaly] = []
        MB = 1024**2

        checks = [
            (active_write, "write_ops", "write_iops", lambda s: s["write_ops"]),
            (active_read, "read_ops", "read_iops", lambda s: s["read_ops"]),
            (active_write, "write_bytes", "write_bandwidth_mbps", lambda s: s["write_bytes"] / MB),
            (active_read, "read_bytes", "read_bandwidth_mbps", lambda s: s["read_bytes"] / MB),
            (active_write, "total_wait_write_ms", "write_latency_ms",
             lambda s: s["total_wait_write_ms"] if s["total_wait_write_ms"] is not None else None),
            (active_read, "total_wait_read_ms", "read_latency_ms",
             lambda s: s["total_wait_read_ms"] if s["total_wait_read_ms"] is not None else None),
        ]

        for sample_set, _raw_key, metric_name, extractor in checks:
            if len(sample_set) < 10:
                continue

            values = []
            timestamps = []
            indices = []
            for i, s in enumerate(sample_set):
                v = extractor(s)
                if v is not None:
                    values.append(v)
                    timestamps.append(s["timestamp_iso"])
                    indices.append(i)

            if len(values) < 10:
                continue

            mean_val = statistics.mean(values)
            std_val = statistics.stdev(values)
            if std_val == 0:
                continue

            for j, (v, ts, idx) in enumerate(zip(values, timestamps, indices)):
                z = (v - mean_val) / std_val
                if abs(z) > self.ANOMALY_THRESHOLD:
                    anomalies.append(Anomaly(
                        index=idx,
                        timestamp=ts,
                        metric=metric_name,
                        value=v,
                        z_score=abs(z),
                        direction="spike" if z > 0 else "drop",
                    ))

        # Sort by z-score descending
        anomalies.sort(key=lambda a: a.z_score, reverse=True)
        return anomalies

    # ── I/O Size Analysis ─────────────────────────────────────

    def _compute_io_sizes(
        self, active_write: List[Dict], active_read: List[Dict]
    ) -> Dict[str, Any]:
        """Compute average KB per I/O operation."""
        result: Dict[str, Any] = {}
        KB = 1024

        # Write op sizes
        w_sizes = []
        for s in active_write:
            if s["write_ops"] > 0 and s["write_bytes"] > 0:
                w_sizes.append(s["write_bytes"] / s["write_ops"] / KB)
        if w_sizes:
            result["write_kb_per_op"] = compute_stats(w_sizes).to_dict()

        # Read op sizes
        r_sizes = []
        for s in active_read:
            if s["read_ops"] > 0 and s["read_bytes"] > 0:
                r_sizes.append(s["read_bytes"] / s["read_ops"] / KB)
        if r_sizes:
            result["read_kb_per_op"] = compute_stats(r_sizes).to_dict()

        return result

    # ── Observations ──────────────────────────────────────────

    def _generate_observations(
        self, analysis: TelemetryPoolAnalysis
    ) -> List[Observation]:
        """Generate neutral observations from telemetry analysis."""
        obs: List[Observation] = []

        # IOPS consistency
        for op, label in [("write_ops", "Write"), ("read_ops", "Read")]:
            stats = analysis.iops.get("active_only", {}).get(op, {})
            cv = stats.get("cv_percent", 0)
            count = stats.get("count", 0)
            if count > 0:
                if cv < 15:
                    consistency = "highly consistent"
                elif cv < 30:
                    consistency = "moderately consistent"
                else:
                    consistency = "variable"
                obs.append(Observation(
                    category=f"telemetry_{label.lower()}_consistency",
                    description=(
                        f"{label} IOPS {consistency} "
                        f"(CV={cv:.1f}%, mean={stats.get('mean', 0):,.0f}, "
                        f"std_dev={stats.get('std_dev', 0):,.0f})"
                    ),
                    data={"cv_percent": cv, "mean": stats.get("mean", 0)},
                ))

        # Anomaly summary
        if analysis.anomalies:
            by_metric: Dict[str, int] = {}
            for a in analysis.anomalies:
                by_metric[a.metric] = by_metric.get(a.metric, 0) + 1
            summary_parts = [f"{m}: {c}" for m, c in sorted(by_metric.items())]
            obs.append(Observation(
                category="telemetry_anomalies",
                description=f"{len(analysis.anomalies)} anomalies detected ({', '.join(summary_parts)})",
                data=by_metric,
            ))

        # Utilization pattern
        summary = analysis.sample_summary
        total_active_pct = (
            summary.get("active_write_pct", 0) + summary.get("active_read_pct", 0)
        )
        if total_active_pct < 50:
            obs.append(Observation(
                category="telemetry_utilization",
                description=(
                    f"Pool active during {total_active_pct:.0f}% of samples "
                    f"(write: {summary.get('active_write_pct', 0):.0f}%, "
                    f"read: {summary.get('active_read_pct', 0):.0f}%)"
                ),
            ))

        # Phase count
        active_phases = [p for p in analysis.phases if p.phase != IOPhase.IDLE]
        if active_phases:
            phase_counts: Dict[str, int] = {}
            for p in active_phases:
                phase_counts[p.phase.value] = phase_counts.get(p.phase.value, 0) + 1
            obs.append(Observation(
                category="telemetry_phases",
                description=(
                    f"Detected {len(active_phases)} active phase segments: "
                    + ", ".join(f"{v} {k}" for k, v in sorted(phase_counts.items()))
                ),
            ))

        # I/O size patterns
        for op, label in [("write_kb_per_op", "Write"), ("read_kb_per_op", "Read")]:
            stats = analysis.io_size_kb.get(op, {})
            if stats.get("count", 0) > 0:
                mean_kb = stats.get("mean", 0)
                if mean_kb >= 1024:
                    size_desc = f"{mean_kb/1024:.1f} MB/op"
                else:
                    size_desc = f"{mean_kb:.0f} KB/op"
                obs.append(Observation(
                    category=f"telemetry_{label.lower()}_io_size",
                    description=f"{label} average I/O size: {size_desc}",
                    data={"mean_kb": mean_kb, "median_kb": stats.get("median", 0)},
                ))

        return obs


# ══════════════════════════════════════════════════════════════
# Result Analyzer (Scaling Analysis - unchanged)
# ══════════════════════════════════════════════════════════════

class ResultAnalyzer:
    """Analyzes TN-Bench results with neutral data presentation."""

    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.pool_analyses: List[PoolAnalysis] = []

    def analyze(self) -> SystemAnalysis:
        """Run full analysis: scaling + telemetry."""
        # Scaling analysis
        for pool in self.results.get("pools", []):
            pa = self._analyze_pool(pool)
            self.pool_analyses.append(pa)

        disk_comparison = self._analyze_disks()

        # Telemetry analysis
        telemetry_analyzer = TelemetryAnalyzer(self.results)
        telemetry_analyses = telemetry_analyzer.analyze()

        return SystemAnalysis(
            pool_analyses=self.pool_analyses,
            disk_comparison=disk_comparison,
            telemetry_analyses=telemetry_analyses,
        )

    def _analyze_pool(self, pool: Dict[str, Any]) -> PoolAnalysis:
        """Analyze a single pool's scaling behavior."""
        name = pool.get("name", "unknown")
        benchmark = pool.get("benchmark", [])
        observations = []

        if not benchmark:
            return PoolAnalysis(
                name=name,
                write_scaling={},
                read_scaling={},
                observations=[]
            )

        # Extract data points
        thread_counts = []
        write_speeds = []
        read_speeds = []

        for b in benchmark:
            thread_counts.append(b.get("threads", 0))
            write_speeds.append(b.get("average_write_speed", 0))
            read_speeds.append(b.get("average_read_speed", 0))

        # Analyze each operation type
        write_scaling = self._analyze_scaling("write", thread_counts, write_speeds, observations, name)
        read_scaling = self._analyze_scaling("read", thread_counts, read_speeds, observations, name)

        return PoolAnalysis(
            name=name,
            write_scaling=write_scaling,
            read_scaling=read_scaling,
            observations=observations
        )

    def _analyze_scaling(self, op_name: str, threads: List[int], speeds: List[float],
                         observations: List[Observation], pool_name: str) -> Dict[str, Any]:
        """Analyze scaling behavior for one operation type."""
        if len(speeds) < 2:
            return {}

        # Build progression table
        progression = []
        for i, (t, s) in enumerate(zip(threads, speeds)):
            progression.append({
                "threads": t,
                "speed_mbps": round(s, 1),
                "vs_single_thread": round(s / speeds[0], 2) if speeds[0] > 0 else 0
            })

        # Calculate deltas between consecutive points
        deltas = []
        for i in range(1, len(speeds)):
            delta = speeds[i] - speeds[i-1]
            pct_change = (delta / speeds[i-1] * 100) if speeds[i-1] > 0 else 0
            deltas.append({
                "from_threads": threads[i-1],
                "to_threads": threads[i],
                "delta_mbps": round(delta, 1),
                "pct_change": round(pct_change, 1)
            })

        # Find peak performance
        max_speed = max(speeds)
        max_idx = speeds.index(max_speed)
        optimal_threads = threads[max_idx]

        # Calculate thread efficiency (speed per thread at peak)
        thread_efficiency = max_speed / optimal_threads if optimal_threads > 0 else 0

        # Identify transitions
        positive_transitions = [d for d in deltas if d["delta_mbps"] > 0]
        negative_transitions = [d for d in deltas if d["delta_mbps"] < 0]

        # Add observations for notable transitions
        for d in deltas:
            if d["pct_change"] < -20:  # Significant drop
                observations.append(Observation(
                    category=f"{op_name}_scaling",
                    description=f"Speed decreases from {d['from_threads']} to {d['to_threads']} threads",
                    data=d
                ))
            elif d["to_threads"] > 8 and d["pct_change"] < 5 and d["delta_mbps"] > 0:
                # Diminishing returns at high thread counts
                observations.append(Observation(
                    category=f"{op_name}_scaling",
                    description=f"Diminishing returns above {d['from_threads']} threads",
                    data=d
                ))

        # Summary observation
        if negative_transitions and not positive_transitions:
            observations.append(Observation(
                category=f"{op_name}_summary",
                description="Performance does not improve with additional threads",
                data={"single_thread": speeds[0], "max_thread": speeds[-1]}
            ))

        return {
            "progression": progression,
            "deltas": deltas,
            "peak_speed_mbps": round(max_speed, 1),
            "optimal_threads": optimal_threads,
            "thread_efficiency": round(thread_efficiency, 1),
            "positive_transitions": len(positive_transitions),
            "negative_transitions": len(negative_transitions)
        }

    def _analyze_disks(self) -> Dict[str, Any]:
        """Compare disk performance within pools using pool-relative metrics."""
        disks = self.results.get("disks", [])
        if not disks:
            return {}

        # Group by pool
        pool_disks = {}
        for disk in disks:
            pool = disk.get("pool", "unassigned")
            if pool not in pool_disks:
                pool_disks[pool] = []

            speed = disk.get("benchmark", {}).get("average_speed", 0)
            pool_disks[pool].append({
                "name": disk.get("name"),
                "model": disk.get("model", "unknown"),
                "speed_mbps": round(speed, 1)
            })

        # Build pool-relative comparison tables
        pool_stats = {}
        for pool, dlist in pool_disks.items():
            if len(dlist) < 2:
                continue

            speeds = [d["speed_mbps"] for d in dlist]
            pool_avg = sum(speeds) / len(speeds)
            pool_min = min(speeds)
            pool_max = max(speeds)

            # Build per-disk comparison
            disk_table = []
            for d in dlist:
                speed = d["speed_mbps"]
                pct_of_pool = (speed / pool_avg * 100) if pool_avg > 0 else 0
                vs_fastest = (speed / pool_max * 100) if pool_max > 0 else 0

                disk_table.append({
                    "disk": d["name"],
                    "model": d["model"],
                    "speed_mbps": speed,
                    "pct_of_pool_avg": round(pct_of_pool, 1),
                    "pct_of_pool_max": round(vs_fastest, 1)
                })

            # Sort by speed
            disk_table.sort(key=lambda x: x["speed_mbps"], reverse=True)

            pool_stats[pool] = {
                "disks": disk_table,
                "pool_average_mbps": round(pool_avg, 1),
                "pool_range_mbps": round(pool_max - pool_min, 1),
                "variance_pct": round((pool_max - pool_min) / pool_avg * 100, 1) if pool_avg > 0 else 0
            }

        return pool_stats


# ══════════════════════════════════════════════════════════════
# CLI Entry Points
# ══════════════════════════════════════════════════════════════

def analyze_results_file(filepath: str) -> Optional[SystemAnalysis]:
    """Analyze a TN-Bench results JSON file (scaling + telemetry)."""
    try:
        with open(filepath, 'r') as f:
            results = json.load(f)

        analyzer = ResultAnalyzer(results)
        return analyzer.analyze()
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return None


def analyze_telemetry_only(filepath: str) -> Optional[List[TelemetryPoolAnalysis]]:
    """Analyze only the telemetry data from a TN-Bench results file."""
    try:
        with open(filepath, 'r') as f:
            results = json.load(f)

        analyzer = TelemetryAnalyzer(results)
        return analyzer.analyze()
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        analysis = analyze_results_file(sys.argv[1])
        if analysis:
            print(json.dumps(analysis.to_dict(), indent=2))
    else:
        print("Usage: python analytics.py <results_file.json>")
