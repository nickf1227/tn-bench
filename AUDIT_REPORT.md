# TN-Bench Code Audit Report

**Date:** 2026-02-07
**Branch:** tn-bench-2.1
**Auditor:** Code audit subagent

## Summary

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| Total Python LOC | 5,797 | ~5,200 | ~-600 |
| Source files (.py) | 16 | 15 | -1 |

## Issues Found & Remediation

### 🔴 Critical: `disk_raw.py` is Dead Code (111 lines)

**Problem:** `DiskBenchmark` from `disk_raw.py` is imported in `truenas-bench.py` and
`benchmarks/__init__.py` but **never instantiated anywhere**. The main script exclusively
uses `EnhancedDiskBenchmark` (line 403). `disk_raw.py` is a strictly-inferior subset of
`disk_enhanced.py` — it only supports 4K sequential reads with no block-size selection,
no parallel mode, and no seek-stress mode.

**Fix:** Remove `disk_raw.py` entirely. Remove all imports/references. The `EnhancedDiskBenchmark`
in serial mode with block_size="1" (4K) is a perfect superset.

---

### 🔴 Duplicate Statistics Functions (2 implementations)

**Problem:** Two nearly identical statistics calculation functions exist:
- `_calculate_stats()` in `core/zpool_iostat_collector.py` (lines 753-800) — returns `dict`
- `compute_stats()` in `core/analytics.py` (lines 279-305) — returns `TelemetryStats`

Both compute: count, mean, median, min, max, std_dev, p50-p99, cv_percent.
The only difference is the return type (dict vs dataclass).

**Fix:** Keep `_calculate_stats` in `zpool_iostat_collector.py` (used by the collector's
`_stats_for_samples` and by tests) and keep `compute_stats` in `analytics.py` (used
by TelemetryAnalyzer). They serve different layers. However, document this architectural
decision. A future cleanup could unify them.

---

### 🔴 Duplicate Bandwidth/Latency Parsers (3 implementations)

**Problem:** Three sets of parsers for bandwidth and latency strings:
1. `_parse_bandwidth_mbps()` + `_parse_latency_ms()` in `zpool_iostat_collector.py`
2. `parse_bandwidth()` + `parse_latency_to_ms()` in `analytics.py`
3. `_parse_value_with_suffix()` in `ZpoolIostatCollector` class

These handle the same ZFS unit-suffixed strings but with slightly different return scales.

**Fix:** Document the architectural boundary. The collector parsers work with native
`ZpoolIostatSample` objects; the analytics parsers work with both native and simplified
formats. Consolidation would create a cross-dependency. Leave as-is with documentation.

---

### 🟡 Dead Functions in `report_generator.py` (~130 lines)

**Problem:** Six functions are defined but never called:
- `_format_iops_section()` (lines 454-476)
- `_format_bandwidth_section()` (lines 478-497)
- `_format_latency_section()` (lines 500-533)
- `_format_queue_section()` (lines 536-567)
- `_format_stats_row()` (lines 436-452) — only called by the above dead functions
- `_cv_rating()` (lines 608-615)

These were superseded when telemetry formatting was consolidated into
`telemetry_formatter.py`. The `_format_telemetry_section()` now delegates to
`TelemetryFormatter` and only keeps markdown-specific "nerd stats" sections.

**Fix:** Remove all six dead functions.

---

### 🟡 Unused Import: `statistics` in `disk_enhanced.py`

**Problem:** `import statistics` on line 8 of `benchmarks/disk_enhanced.py` is never used.

**Fix:** Remove the import.

---

### 🟡 Bug: `print_error` Used But Not Imported in `disk_enhanced.py`

**Problem:** Line 107 calls `print_error()` but the import on line 9-12 does not include it.
This would cause a `NameError` if an unknown test mode were passed.

**Fix:** Add `print_error` to the import list.

---

### 🟡 Duplicate `run_dd_read_command` Functions

**Problem:** Two separate `run_dd_read_command()` functions:
- `benchmarks/disk_raw.py` line 14 — hardcoded 4K block size
- `benchmarks/disk_enhanced.py` line 24 — configurable block size

**Fix:** Removing `disk_raw.py` eliminates this duplication.

---

### 🟡 Duplicate `color_text` Definitions (3 implementations)

**Problem:**
- `utils/__init__.py` — canonical, checks `isatty()`
- `core/telemetry_formatter.py` — standalone copy for formatter module
- `core/zpool_iostat_collector.py` — fallback no-op for standalone testing

**Fix:** The formatter's copy exists to avoid importing `utils` (which would create a
dependency on the full TN-Bench project). The collector's fallback is intentional for
standalone testing. Document but leave as-is.

---

### 🟢 Minor: `calculate_dwpd()` in `truenas-bench.py`

**Problem:** Utility function defined in the main script rather than in `utils/` or `core/`.

**Fix:** Low priority. It's only used once and is specific to the main flow.
Leave as-is but note for future refactoring.

---

## Changes Implemented

1. **Deleted `benchmarks/disk_raw.py`** — dead code, 111 lines removed
2. **Updated `benchmarks/__init__.py`** — removed DiskBenchmark import/export
3. **Updated `truenas-bench.py`** — removed DiskBenchmark import
4. **Removed 6 dead functions from `report_generator.py`** — ~130 lines removed
5. **Fixed `disk_enhanced.py`** — removed unused `statistics` import, added missing `print_error` import
6. **Added architectural comments** throughout to document design decisions
