# TN-Bench Analytics Report

**Source:** `./tn_bench_results.json`
**Generated:** 2026-02-07 17:32:30

## Metrics Glossary

This report analyzes zpool iostat telemetry collected during the benchmark. Below are definitions for the metrics and statistics presented.

### IOPS (Input/Output Operations Per Second)

- **Write IOPS**: Number of write operations completed per second. Higher is better for write-heavy workloads.
- **Read IOPS**: Number of read operations completed per second. Higher is better for read-heavy workloads.
- **Total IOPS**: Combined read + write operations per second.

### Bandwidth (Throughput)

- **Write Bandwidth**: Data write speed in MB/s (megabytes per second). This includes ZFS overhead (parity for RAIDZ, mirroring, etc.) and may not match the raw benchmark speed.
- **Read Bandwidth**: Data read speed in MB/s. Higher is better.
- **Note**: Bandwidth from zpool iostat reflects actual ZFS pool activity, including metadata, compression, and redundancy overhead.

### Latency (Wait Times)

- **Total Wait**: Total time from I/O request submission to completion (ms). Lower is better. Includes queue time + disk time.
- **Disk Wait**: Time spent actively reading/writing to disk (ms). Lower is better. Excludes queue time.
- **Async Queue Wait**: Time spent in ZFS async write queue (ms). Non-blocking writes may show 0 here.
- **Sync Queue Wait**: Time spent in ZFS sync write queue (ms). Important for synchronous workloads (databases, NFS).

### Statistical Measures

- **Mean (Average)**: The arithmetic average of all samples. Calculated by adding all values and dividing by the count. Represents typical performance but can be skewed by outliers.

- **Median**: The middle value when all samples are sorted in order. Half the samples are above this value, half are below. Less affected by extreme outliers than the mean.

- **P99 (99th Percentile)**: The value below which 99% of all samples fall. Only 1% of samples exceed this value. Useful for identifying worst-case performance ('tail latency').

- **Std Dev (Standard Deviation)**: Measures how spread out values are from the mean. Higher = more variable performance. Lower = more consistent. Calculated as the square root of the variance.

- **CV% (Coefficient of Variation)**: A normalized measure of consistency calculated as: **Std Dev ÷ Mean × 100**. This allows comparison across different scales.

  **Consistency Guidelines:**
  - **< 10%**: Very consistent (excellent)
  - **10-20%**: Moderately consistent (good)
  - **20-30%**: Variable (acceptable)
  - **> 30%**: Highly variable (may indicate issues)

### Activity Phases

The benchmark timeline is segmented into phases based on I/O activity:

- **IDLE**: No I/O activity detected. Occurs between test iterations or during setup/teardown.
- **WRITE**: Active write operations. Benchmark is writing test data.
- **READ**: Active read operations. Benchmark is reading/verifying data.
- **MIXED**: Both read and write operations active simultaneously. Typically seen during phase transitions.

Statistics are reported separately for 'all samples' and 'active only' (excluding IDLE periods) to show true performance during I/O.

### Anomaly Detection

Statistical outliers detected using **z-score analysis**. The z-score measures how many standard deviations a value is from the mean.

**Z-Score Interpretation:**
- **|z| < 2**: Normal variation (within 95% of data)
- **|z| > 3**: Statistical outlier (anomaly) — only 0.3% of normal data falls here
- **Positive z**: Value is above average
- **Negative z**: Value is below average

**Anomaly Types:**
- **Spike**: Sudden increase in IOPS/bandwidth or latency
- **Drop**: Sudden decrease in IOPS/bandwidth

Most anomalies occur at phase transitions (ramp-up/ramp-down) and are normal. Sustained anomalies during steady-state may indicate performance issues.

### I/O Size Analysis

- **KB/op**: Average kilobytes per operation. Indicates sequential (large) vs random (small) I/O patterns.
- TN-Bench uses large sequential I/O (~900KB-1MB per operation).

---

## Pool: fire

### Write Scaling

- **Peak Performance:** 2781.9 MB/s at 20 threads
- **Thread Efficiency:** 139.1 MB/s per thread
- **Scaling Transitions:** 2 positive, 1 negative

| Threads | Speed (MB/s) | vs Single-Thread |
|---------|-------------|------------------|
| 1 | 225.8 | 1.0x |
| 10 | 2039.1 | 9.03x |
| 20 | 2781.9 | 12.32x |
| 40 | 2756.2 | 12.21x |

**Thread Count Transitions:**

| From | To | Δ Speed | % Change |
|------|----|---------|----------|
| 1 | 10 | +1813.3 | +803.2% |
| 10 | 20 | +742.8 | +36.4% |
| 20 | 40 | -25.7 | -0.9% |

### Read Scaling

- **Peak Performance:** 6621.8 MB/s at 40 threads
- **Thread Efficiency:** 165.5 MB/s per thread
- **Scaling Transitions:** 3 positive, 0 negative

| Threads | Speed (MB/s) | vs Single-Thread |
|---------|-------------|------------------|
| 1 | 2788.9 | 1.0x |
| 10 | 6513.1 | 2.34x |
| 20 | 6612.8 | 2.37x |
| 40 | 6621.8 | 2.37x |

**Thread Count Transitions:**

| From | To | Δ Speed | % Change |
|------|----|---------|----------|
| 1 | 10 | +3724.2 | +133.5% |
| 10 | 20 | +99.7 | +1.5% |
| 20 | 40 | +9.0 | +0.1% |

### Observations

- Diminishing returns above 10 threads
- Diminishing returns above 20 threads

## Pool: ice

## Disk Comparison

Per-disk performance relative to pool average.

### Pool: N/A

- **Pool Average:** 0.0 MB/s
- **Variance:** 0%

| Disk | Model | Speed (MB/s) | % of Pool Avg | % of Pool Max |
|------|-------|-------------|---------------|---------------|
| sdan | KINGSTON_SA400S37120G | 0 | 0% | 0% |
| sdb | HUSMH842_CLAR200 | 0 | 0% | 0% |
| sda | HUSMH842_CLAR200 | 0 | 0% | 0% |
| sdab | HUH721010AL42C0 | 0 | 0% | 0% |
| sdc | HUH721010AL42C0 | 0 | 0% | 0% |

### Pool: fire

- **Pool Average:** 0.0 MB/s
- **Variance:** 0%

| Disk | Model | Speed (MB/s) | % of Pool Avg | % of Pool Max |
|------|-------|-------------|---------------|---------------|
| nvme0n1 | INTEL SSDPE2KE016T8 | 0 | 0% | 0% |
| nvme2n1 | INTEL SSDPE2KE016T8 | 0 | 0% | 0% |
| nvme3n1 | SAMSUNG MZWLL1T6HEHP-0000 | 0 | 0% | 0% |
| nvme1n1 | SAMSUNG MZWLL1T6HEHP-0000 | 0 | 0% | 0% |

### Pool: ice

- **Pool Average:** 0.0 MB/s
- **Variance:** 0%

| Disk | Model | Speed (MB/s) | % of Pool Avg | % of Pool Max |
|------|-------|-------------|---------------|---------------|
| sdo | HUS728T8TAL4204 | 0 | 0% | 0% |
| sds | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdz | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdaa | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdn | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdv | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdr | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdt | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdu | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdw | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdx | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdy | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdac | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdal | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdam | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdad | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdae | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdaf | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdag | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdah | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdai | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdaj | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdak | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdd | HUS728T8TAL4204 | 0 | 0% | 0% |
| sde | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdp | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdi | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdf | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdl | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdj | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdh | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdg | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdm | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdk | HUS728T8TAL4204 | 0 | 0% | 0% |
| sdq | HUS728T8TAL4204 | 0 | 0% | 0% |

## Telemetry: fire

## Telemetry Analysis: Pool `fire`

- Total samples: 173  |  Steady-state samples: 346

### Per-Thread-Count Steady-State Analysis

> **Note:** WRITE telemetry only - READ metrics excluded due to ZFS ARC cache interference, which can artificially inflate read performance numbers.

**1T-write** (173 samples):

| Metric | Mean | Median | P99 (Rating) | Std Dev (Rating) | CV% (Rating) |
|--------|------|--------|--------------|------------------|--------------|
| IOPS | 7686.2 | 10200.0 | 16200.0 (High) | 5753.2 (High Variance) | 74.8% (High Variance) |

| Metric | Mean | Median | P99 (Rating) | Std Dev (Rating) | CV% (Rating) |
|--------|------|--------|--------------|------------------|--------------|
| Bandwidth (MB/s) | 2211.0 | 3041.3 | 4147.2 (High) | 1721.8 (High Variance) | 77.9% (High Variance) |



### Legend

**Statistical Measures:**

| Measure | Definition |
|---------|------------|
| **Mean** | Average of all samples |
| **Median** | Middle value (50th percentile), less affected by outliers |
| **P99** | 99th percentile - 99% of samples fall below this value |
| **Std Dev** | Standard deviation - measures spread/consistency |
| **CV%** | Coefficient of Variation (std dev / mean × 100) |

**Rating Guides:**

| Metric | Excellent | Good | Variable/Acceptable | High/High Variance |
|--------|-----------|------|---------------------|-------------------|
| **CV%** | < 10% | 10-20% | 20-30% | > 30% |
| **P99 Latency** | < 10ms | < 50ms | < 100ms | > 100ms |
| **Std Dev** | Low | Moderate | Noticeable | Wide |

*Lower is better for P99 Latency and Std Dev. CV% is normalized.*

### Sample Summary

| Metric | Count | % of Total |
|--------|------:|----------:|
| Total Samples | 173 | 100% |
| Active Write | 173 | 100.0% |
| Active Read | 173 | 100.0% |
| Idle | 0 | 0.0% |

### I/O Size Analysis

| Operation | Samples | Mean (KB) | Median (KB) | P99 (KB) | Min (KB) | Max (KB) | CV |
|-----------|--------:|----------:|------------:|---------:|---------:|---------:|---:|
| Write | 173 | 201.4 | 280.0 | 335.5 | 5.4 | 337.2 | 67.6% |
| Read | 173 | 97.1 | 12.2 | 350.2 | 4.0 | 350.2 | 150.9% |

### Anomaly Detection

No statistical anomalies detected (threshold: z > 3.0).

### Capacity

| Metric | GiB |
|--------|----:|
| Start | 1566.72 |
| End | 2631.68 |
| Peak | 2631.68 |
| Min | 1566.72 |
