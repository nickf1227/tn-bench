# Sample Data

Real benchmark results for regression testing and development reference.

## Systems

### `prod/` — prod.fusco.me
- **Pool:** inferno (10x NVMe RAIDZ1, ~4.36 TiB)
- **CPU:** High core count
- **Use case:** Production NVMe array performance baseline

### `m50/` — m50
- **Pool:** Mixed storage
- **Use case:** Secondary system performance baseline

## Files

| File | Description |
|------|-------------|
| `tn_bench_results.json` | Raw benchmark output (includes telemetry samples) |
| `tn_bench_results_analytics.json` | Post-hoc analytics (scaling, anomalies, phases) |
| `tn_bench_results_report.md` | Human-readable markdown report |

## Usage

These files can be used for:
- Regression testing formatter/report changes against real data
- Validating analytics pipeline without running full benchmarks
- Comparing output before/after code changes
