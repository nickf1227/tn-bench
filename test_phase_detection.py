#!/usr/bin/env python3
"""
Test the phase detection system against production telemetry data.

Loads tnbench-merge-prod.json, reconstructs ZpoolIostatTelemetry objects,
runs post-hoc phase detection, and prints before/after CV% comparison.
"""

import json
import sys
import os

# Ensure we can import from the tn-bench package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.zpool_iostat_collector import (
    ZpoolIostatSample,
    ZpoolIostatTelemetry,
    Phase,
    PhaseDetector,
    run_phase_detection_posthoc,
    calculate_zpool_iostat_summary,
    _calculate_stats,
)

RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "results", "tnbench-merge-prod.json"
)


def load_production_telemetry() -> ZpoolIostatTelemetry:
    """Load and reconstruct telemetry from the production JSON."""
    with open(RESULTS_PATH) as f:
        data = json.load(f)

    telem_raw = data["pools"][0]["zpool_iostat_telemetry"]
    samples = []
    for s in telem_raw["samples"]:
        samples.append(ZpoolIostatSample(**s))

    telemetry = ZpoolIostatTelemetry(
        pool_name=telem_raw["pool_name"],
        start_time=telem_raw["start_time"],
        start_time_iso=telem_raw["start_time_iso"],
        end_time=telem_raw["end_time"],
        end_time_iso=telem_raw["end_time_iso"],
        warmup_iterations=telem_raw["warmup_iterations"],
        cooldown_iterations=telem_raw["cooldown_iterations"],
        samples=samples,
    )
    return telemetry


def test_phase_detector_basic():
    """Test the PhaseDetector with synthetic data."""
    print("=" * 70)
    print("TEST 1: PhaseDetector with synthetic data")
    print("=" * 70)

    detector = PhaseDetector(
        idle_threshold=500,
        active_threshold=5000,
        steady_cv_max=50.0,
        window_size=3,
        min_hold_samples=2,
    )

    # Simulate: idle → warmup → steady → cooldown → idle
    synthetic = (
        [0, 10, 5]                     # idle
        + [2000, 5000, 8000]           # warmup/transition
        + [10000, 10500, 9800, 10200, 10100, 9900, 10300, 10000]  # steady
        + [5000, 2000, 500]            # cooldown
        + [10, 0, 0]                   # idle
    )

    t = 1000.0
    for iops in synthetic:
        phase = detector.push(iops, t)
        print(f"  t={t:.0f}  iops={iops:>8}  phase={phase.value}")
        t += 1.0

    spans = detector.finalize()
    print(f"\n  Detected {len(spans)} spans:")
    for sp in spans:
        print(f"    {sp.phase:<14} samples={sp.sample_count:>3}  duration={sp.duration:.1f}s")

    # Check that we got at least idle, steady_state, and idle
    phase_names = [sp.phase for sp in spans]
    assert Phase.IDLE.value in phase_names, "Should detect IDLE phase"
    assert Phase.STEADY_STATE.value in phase_names, "Should detect STEADY_STATE phase"
    print("\n  ✅ PASSED\n")


def test_production_posthoc():
    """Run post-hoc phase detection on production data and verify CV improvement."""
    print("=" * 70)
    print("TEST 2: Post-hoc phase detection on production data")
    print("=" * 70)

    telemetry = load_production_telemetry()
    print(f"  Loaded {len(telemetry.samples)} samples, duration {telemetry.end_time - telemetry.start_time:.0f}s")

    # Before phase detection: compute all-samples CV
    all_total_iops = [
        s.operations_read + s.operations_write for s in telemetry.samples
    ]
    before_stats = _calculate_stats(all_total_iops)
    print(f"\n  BEFORE phase detection:")
    print(f"    All samples: n={before_stats['count']}  mean={before_stats['mean']:.0f}  CV={before_stats['cv_percent']:.1f}%")

    # Run phase detection
    run_phase_detection_posthoc(telemetry)

    # After: show phase breakdown
    print(f"\n  Phase breakdown:")
    phase_counts = {}
    for s in telemetry.samples:
        phase_counts[s.phase] = phase_counts.get(s.phase, 0) + 1
    for phase_name, count in sorted(phase_counts.items()):
        pct = count / len(telemetry.samples) * 100
        print(f"    {phase_name:<14} {count:>4} samples ({pct:.1f}%)")

    # After: compute steady-state-only CV
    ss_samples = telemetry.get_steady_state_samples()
    if ss_samples:
        ss_total_iops = [s.operations_read + s.operations_write for s in ss_samples]
        after_stats = _calculate_stats(ss_total_iops)
        print(f"\n  AFTER phase detection (steady-state only):")
        print(f"    Steady-state: n={after_stats['count']}  mean={after_stats['mean']:.0f}  CV={after_stats['cv_percent']:.1f}%")
        improvement = before_stats['cv_percent'] - after_stats['cv_percent']
        print(f"\n  CV% improvement: {before_stats['cv_percent']:.1f}% → {after_stats['cv_percent']:.1f}%  (Δ = {improvement:+.1f}%)")
    else:
        print("\n  ⚠️  No steady-state samples detected!")

    # Phase spans
    print(f"\n  Phase spans ({len(telemetry.phase_spans)}):")
    for sp in telemetry.phase_spans:
        print(f"    {sp.phase:<14} idx=[{sp.start_index}..{sp.end_index}]  "
              f"samples={sp.sample_count:>3}  duration={sp.duration:.1f}s")

    print("\n  ✅ PASSED\n")


def test_full_summary():
    """Test the full calculate_zpool_iostat_summary output."""
    print("=" * 70)
    print("TEST 3: Full summary with phase detection")
    print("=" * 70)

    telemetry = load_production_telemetry()
    run_phase_detection_posthoc(telemetry)
    summary = calculate_zpool_iostat_summary(telemetry)

    print(f"  Pool: {summary['pool_name']}")
    print(f"  Total samples: {summary['total_samples']}")
    print(f"  Steady-state samples: {summary['steady_state_samples']}")
    print(f"  Duration: {summary['duration_seconds']}s")

    # All-samples IOPS
    all_iops = summary['all_samples']['iops']['total_all']
    print(f"\n  All-samples total IOPS:")
    print(f"    Mean={all_iops['mean']:.0f}  P99={all_iops['p99']:.0f}  CV={all_iops['cv_percent']:.1f}%")

    # Steady-state IOPS
    if summary['steady_state']:
        ss_iops = summary['steady_state']['iops']['total_all']
        print(f"\n  Steady-state total IOPS:")
        print(f"    Mean={ss_iops['mean']:.0f}  P99={ss_iops['p99']:.0f}  CV={ss_iops['cv_percent']:.1f}%")

    # Phase detection info
    pd = summary.get('phase_detection', {})
    print(f"\n  Phases detected: {pd.get('total_phases_detected', 0)}")
    for phase_name, info in pd.get('breakdown', {}).items():
        print(f"    {phase_name:<14} {info['sample_count']:>4} samples  {info['duration_seconds']:>7.1f}s  ({info['percent_of_total']:.1f}%)")

    print("\n  ✅ PASSED\n")


def test_sample_phase_fields():
    """Verify that sample objects get phase and segment_label fields."""
    print("=" * 70)
    print("TEST 4: Sample phase/segment_label fields")
    print("=" * 70)

    telemetry = load_production_telemetry()
    run_phase_detection_posthoc(telemetry)

    phases_found = set(s.phase for s in telemetry.samples)
    print(f"  Unique phases on samples: {phases_found}")
    assert len(phases_found) > 1, "Should have more than one phase"

    # Check that every sample has a phase
    unphased = [i for i, s in enumerate(telemetry.samples) if not s.phase]
    assert len(unphased) == 0, f"All samples should have a phase, but {len(unphased)} are empty"

    print("  ✅ PASSED\n")


def test_to_dict_includes_phases():
    """Verify to_dict() output includes phase detection data."""
    print("=" * 70)
    print("TEST 5: to_dict() includes phase_detection")
    print("=" * 70)

    telemetry = load_production_telemetry()
    run_phase_detection_posthoc(telemetry)
    d = telemetry.to_dict(sample_interval=5)

    assert "phase_detection" in d, "to_dict should include phase_detection"
    pd = d["phase_detection"]
    assert "breakdown" in pd, "phase_detection should include breakdown"
    assert "spans" in pd, "phase_detection should include spans"
    print(f"  phase_detection keys: {list(pd.keys())}")
    print(f"  breakdown phases: {list(pd['breakdown'].keys())}")
    print(f"  spans count: {len(pd['spans'])}")

    # Check samples have phase field
    for s in d["samples"][:3]:
        assert "phase" in s, "Sample dict should include phase field"
        print(f"  Sample phase: {s['phase']}")

    print("  ✅ PASSED\n")


if __name__ == "__main__":
    test_phase_detector_basic()
    test_production_posthoc()
    test_full_summary()
    test_sample_phase_fields()
    test_to_dict_includes_phases()

    print("=" * 70)
    print("ALL TESTS PASSED ✅")
    print("=" * 70)
