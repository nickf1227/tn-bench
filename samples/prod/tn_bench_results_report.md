# TN-Bench Analytics Report

**Source:** `./tn_bench_results.json`
**Generated:** 2026-02-07 17:31:48

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

## Pool: inferno

### Write Scaling

- **Peak Performance:** 4214.0 MB/s at 16 threads
- **Thread Efficiency:** 263.4 MB/s per thread
- **Scaling Transitions:** 2 positive, 1 negative

| Threads | Speed (MB/s) | vs Single-Thread |
|---------|-------------|------------------|
| 1 | 334.5 | 1.0x |
| 8 | 2467.5 | 7.38x |
| 16 | 4214.0 | 12.6x |
| 32 | 4148.0 | 12.4x |

**Thread Count Transitions:**

| From | To | Δ Speed | % Change |
|------|----|---------|----------|
| 1 | 8 | +2133.1 | +637.8% |
| 8 | 16 | +1746.5 | +70.8% |
| 16 | 32 | -66.0 | -1.6% |

### Read Scaling

- **Peak Performance:** 12799.1 MB/s at 16 threads
- **Thread Efficiency:** 799.9 MB/s per thread
- **Scaling Transitions:** 2 positive, 1 negative

| Threads | Speed (MB/s) | vs Single-Thread |
|---------|-------------|------------------|
| 1 | 6569.2 | 1.0x |
| 8 | 12731.0 | 1.94x |
| 16 | 12799.1 | 1.95x |
| 32 | 8098.1 | 1.23x |

**Thread Count Transitions:**

| From | To | Δ Speed | % Change |
|------|----|---------|----------|
| 1 | 8 | +6161.8 | +93.8% |
| 8 | 16 | +68.2 | +0.5% |
| 16 | 32 | -4701.0 | -36.7% |

### Observations

- Diminishing returns above 8 threads
- Speed decreases from 16 to 32 threads

## Pool: plex

## Disk Comparison

Per-disk performance relative to pool average.

### Pool: inferno

- **Pool Average:** 0.0 MB/s
- **Variance:** 0%

| Disk | Model | Speed (MB/s) | % of Pool Avg | % of Pool Max |
|------|-------|-------------|---------------|---------------|
| nvme4n1 | INTEL SSDPE21D960GA | 0 | 0% | 0% |
| nvme7n1 | INTEL SSDPE21D960GA | 0 | 0% | 0% |
| nvme6n1 | INTEL SSDPE21D960GA | 0 | 0% | 0% |
| nvme9n1 | INTEL SSDPE21D960GA | 0 | 0% | 0% |
| nvme5n1 | INTEL SSDPE21D960GA | 0 | 0% | 0% |

### Pool: plex

- **Pool Average:** 0.0 MB/s
- **Variance:** 0%

| Disk | Model | Speed (MB/s) | % of Pool Avg | % of Pool Max |
|------|-------|-------------|---------------|---------------|
| nvme0n1 | SAMSUNG MZVL2512HCJQ-00BL | 0 | 0% | 0% |
| nvme1n1 | SAMSUNG MZVL2512HCJQ-00BL | 0 | 0% | 0% |
| nvme2n1 | SAMSUNG MZVL2512HCJQ-00BL | 0 | 0% | 0% |
| nvme3n1 | SAMSUNG MZVL2512HCJQ-00BL | 0 | 0% | 0% |

## Telemetry: inferno

## Telemetry Analysis: Pool `inferno`

- Total samples: 98  |  Steady-state samples: 175

### Per-Thread-Count Steady-State Analysis

> **Note:** WRITE telemetry only - READ metrics excluded due to ZFS ARC cache interference, which can artificially inflate read performance numbers.

**16T-write** (12 samples):

| Metric | Mean | Median | P99 (Rating) | Std Dev (Rating) | CV% (Rating) |
|--------|------|--------|--------------|------------------|--------------|
| IOPS | 13608.3 | 13650.0 | 14200.0 (High) | 302.9 (Good) | 2.2% (Excellent) |

| Metric | Mean | Median | P99 (Rating) | Std Dev (Rating) | CV% (Rating) |
|--------|------|--------|--------------|------------------|--------------|
| Bandwidth (MB/s) | 3065.2 | 3072.0 | 3184.6 (High) | 55.3 (Excellent) | 1.8% (Excellent) |


**1T-write** (5 samples):

| Metric | Mean | Median | P99 (Rating) | Std Dev (Rating) | CV% (Rating) |
|--------|------|--------|--------------|------------------|--------------|
| IOPS | 3649.8 | 4510.0 | 4620.0 (High) | 2036.0 (High Variance) | 55.8% (High Variance) |

| Metric | Mean | Median | P99 (Rating) | Std Dev (Rating) | CV% (Rating) |
|--------|------|--------|--------------|------------------|--------------|
| Bandwidth (MB/s) | 816.6 | 1021.0 | 1022.0 (High) | 456.4 (Good) | 55.9% (High Variance) |



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
| Total Samples | 98 | 100% |
| Active Write | 80 | 81.6% |
| Active Read | 95 | 96.9% |
| Idle | 0 | 0.0% |

### I/O Size Analysis

| Operation | Samples | Mean (KB) | Median (KB) | P99 (KB) | Min (KB) | Max (KB) | CV |
|-----------|--------:|----------:|------------:|---------:|---------:|---------:|---:|
| Write | 80 | 135.8 | 221.5 | 236.5 | 9.2 | 236.5 | 73.7% |
| Read | 95 | 43.4 | 6.0 | 263.2 | 4.1 | 263.2 | 200.4% |

### Anomaly Detection

**6 anomalies detected** (z-score > 3.0):

**read_latency_ms** (2 anomalies):

| Timestamp | Value | Z-Score | Direction |
|-----------|------:|--------:|-----------|
| 2026-02-07T14:29:23 | 168.00 | 4.36 | spike |
| 2026-02-07T14:29:28 | 143.00 | 3.64 | spike |

**write_latency_ms** (4 anomalies):

| Timestamp | Value | Z-Score | Direction |
|-----------|------:|--------:|-----------|
| 2026-02-07T14:29:38 | 197.00 | 3.62 | spike |
| 2026-02-07T14:29:28 | 196.00 | 3.60 | spike |
| 2026-02-07T14:29:23 | 195.00 | 3.58 | spike |
| 2026-02-07T14:29:33 | 190.00 | 3.48 | spike |

### Capacity

| Metric | GiB |
|--------|----:|
| Start | 3368.96 |
| End | 4198.40 |
| Peak | 4198.40 |
| Min | 3368.96 |
