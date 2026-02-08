# tn-bench v2.2

##  tn-bench is an OpenSource software script that benchmarks your system and collects various statistical information via the TrueNAS API. It creates a dataset in each of your pools during testing, consuming 20 GiB of space for each thread in your system.

## 🆕 What's New in v2.2

### ARC Statistics Telemetry (arcstat)
- Real-time ZFS ARC monitoring during READ benchmark phases
- Measures cache hit rate, ARC size, MRU/MFU distribution, and prefetch effectiveness
- Auto-detects L2ARC presence — L2ARC metrics omitted entirely on systems without cache devices
- Per-thread-count analysis shows how ARC performance changes with workload scale

### Enhanced Zpool Latency Analytics
- **Fixed critical column mapping bug**: `zpool iostat -l` fields are interleaved read/write pairs, not grouped by type
- **Latency unit auto-scaling**: Displays μs when mean < 1ms (NVMe-class storage), ms otherwise
- Per-thread-count latency breakdown with P99 ratings and CV% consistency metrics

### L2ARC Auto-Detection
- Detects cache devices via `zpool status` before starting telemetry collection
- Prevents arcstat crashes on systems without L2ARC hardware
- Dynamic field list: 18 fields (core + zfetch) without L2ARC, 21 fields with L2ARC

## Previous: What's New in v2.1

### Automatic Analytics
- Post-benchmark analysis automatically identifies scaling patterns
- Generates `_analytics.json` with structured performance data
- Generates `_report.md` with human-readable markdown tables
- Neutral data presentation — reports observations without judgment

### Delta-Based Scaling Analysis
- Tracks performance changes between thread count steps
- Identifies optimal thread count for each pool
- Shows thread efficiency (MB/s per thread at peak)
- Highlights notable transitions (gains, losses, plateaus)

### Per-Disk Pool Comparison
- Compares individual disk performance to pool average
- Shows variance percentage within each pool
- Identifies outliers using % of pool max metric

### Unified Telemetry Formatter
- Single source of truth for console UI and markdown reports
- Console output is now a "live preview" of the report content
- Consistent formatting, CV% ratings, and table layouts
- Future changes only need to happen in one place

### Codebase Audit & Cleanup
- Consolidated disk benchmark modules (removed `disk_raw.py`)
- Removed ~250 lines of dead/stale code
- Unified duplicate formatting logic
- Reduced total module count from 16 to 15
- Fixed edge-case bug in error handling

## Previous: What's New in v2.0

### Modular Architecture

tn-bench v2.0 has been completely refactored into a modular architecture. While the user experience remains identical to v1.x, the underlying codebase is now organized into clean, maintainable modules:

```
tn-bench/
├── truenas-bench.py          # Main coordinator (thin UI layer)
├── core/                     # Core functionality
│   ├── __init__.py          # System/pool/disk API calls
│   ├── dataset.py           # Dataset lifecycle management
│   ├── results.py           # JSON output handling
│   ├── analytics.py         # Scaling analysis engine (v2.1)
│   ├── report_generator.py  # Markdown report generation (v2.1)
│   ├── telemetry_formatter.py  # Unified console/markdown formatter (v2.1)
│   └── zpool_iostat_collector.py  # ZFS pool iostat telemetry (v2.1)
├── benchmarks/              # Benchmark implementations
│   ├── __init__.py          # Exports benchmark classes
│   ├── base.py              # Abstract base class
│   ├── zfs_pool.py          # ZFS pool write/read benchmark
│   └── disk_enhanced.py     # Individual disk benchmark (v2.0)
└── utils/                   # Common utilities
    └── __init__.py          # Colors, formatting, print functions
```

**Benefits of this design:**
- **Easier Maintenance**: Each component is isolated and testable
- **Simple Extensibility**: New benchmarks can be added by inheriting from `BenchmarkBase`
- **Clear Separation**: UI, core logic, and benchmarks are cleanly separated
- **Reusable Components**: Core utilities can be shared across benchmarks

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed documentation on the modular design.

## Features

- **Modular Architecture**: Clean separation between UI, core logic, and benchmarks
- **Enhanced Disk Benchmarking**: Multiple test modes (serial, parallel, seek-stress) and configurable block sizes
- Collects system information using TrueNAS API.
- Benchmarks system performance using `dd` command.
- Provides detailed information about system, pools, and disks.
- Supports multiple pools with interactive selection.
- Configurable iteration counts for both pool and disk benchmarks.
- Space validation before running benchmarks.
- Drive Writes Per Day (DWPD) calculation for pool benchmarks.
- Colorized output for better readability.
- JSON output with structured schema for sharing results.
- **Extensible**: Easy to add new benchmark types via the `BenchmarkBase` class


### Running the Script is a simple git clone
### Please note, this script needs to be run as `root`. 

**Interactive Mode (default):**
   ```
   git clone -b tn-bench-2.2 https://github.com/nickf1227/tn-bench.git && cd tn-bench && python3 truenas-bench.py
   ```

**Unattended Mode (v2.3+):**
For automated runs, CI/CD, or batch testing, use `--unattended` with CLI arguments:
   ```
   python3 truenas-bench.py --unattended --pools all --zfs-iterations 2 --disk-iterations 0 --confirm
   ```

See [Unattended Mode](#unattended-mode-v23) section for full CLI reference.

NOTE: `/dev/urandom` generates inherently uncompressible data, the the value of the compression options above is minimal in the current form.

The script will display system and pool information, then prompt you to continue with the benchmarks. Follow the prompts to complete the benchmarking process.


### Benchmarking Process

- **Dataset Creation**: The script creates a temporary dataset in each pool. The dataset is created with a 1M Record Size with no Compression and sync=Disabled using `midclt call pool.dataset.create`
- **Space Validation**: Before running benchmarks, the script checks available space in the dataset and warns if insufficient (requires 20 GiB × thread count). You can choose to proceed anyway or skip the pool.
- **Pool Write Benchmark**: The script performs write benchmarks using `dd` across four thread-count configurations (1, cores÷4, cores÷2, and cores). Each configuration runs N times (configurable, default 2). We use `/dev/urandom` as our input file, so CPU performance may be relevant. This is by design as `/dev/zero` is flawed for this purpose, and CPU stress is expected in real-world use anyway. The data is written in 1M chunks to a dataset with a 1M record size. For each thread, 20G of data is written. This scales with the number of threads, so a system with 16 Threads would write 320G of data per iteration.
- **Pool Read Benchmark**: The script performs read benchmarks using `dd` across the same four thread-count configurations. We are using `/dev/null` as our output file, so RAM speed may be relevant. The data is read in 1M chunks from a dataset with a 1M record size. For each thread, the previously written 20G of data is read.
- **DWPD Calculation**: After each pool's benchmarks complete, the script calculates Drive Writes Per Day (DWPD) based on total data written, pool capacity, and test duration.

**NOTE:** ZFS ARC will also be used and will impact your results. This may be undesirable in some circumstances, and the `zfs_arc_max` can be set to `1` (which means 1 byte) to prevent ARC from caching. Setting it back to `0` will restore the default behavior, but the system will need to be restarted!

I have tested several permutations of file sizes on a dozen systems with varying amount of storage types, space, and RAM. Eventually settled on the current behavior for several reasons. Primarily, I wanted to reduce the impact of, but not REMOVE the ZFS ARC, since in a real world scenario, you would be leveraging the benefits of ARC caching. However, in order to avoid insanely unrealistic results, I needed to use file sizes that saturate the ARC completely. I believe this gives us the best data possible. 


Example of `arcstat -f time,hit%,dh%,ph%,mh% 10` running while the benchmark is running.
<img src="https://github.com/user-attachments/assets/4bdeea59-c88c-46b1-b17a-939594c4eda1" width="50%" />


- **Disk Benchmark**: The script performs sequential read benchmarks on individual disks using `dd`. The read size is calculated as `min(system RAM, disk size)` to work around ARC caching. Data is read in 4K chunks to `/dev/null`, making this a 4K sequential read test. 4K was chosen because `ashift=12` for all recent ZFS pools created in TrueNAS. The number of iterations is configurable (default 2). Run-to-run variance is expected, particularly on SSDs, as data may end up in internal caches.

### Enhanced Disk Benchmark (v2.0)

tn-bench v2.0 introduces an enhanced disk benchmark with multiple test modes and configurable block sizes:

**Test Modes:**
- **SERIAL** (default): Test disks one at a time
  - Best for baseline performance measurements
  - Minimal system impact
  - Recommended for production systems
  
- **PARALLEL**: Test all disks simultaneously
  - Stress tests storage controllers and backplanes
  - Higher resource usage than serial mode
  - Useful for identifying controller bottlenecks
  
- **SEEK_STRESS**: Multiple threads per disk
  - Heavy stress on disk seek mechanisms
  - Can saturate CPU cores
  - May cause system instability on busy systems
  - Not recommended for production use

**Block Size Options:**
- 4K (small random I/O)
- 32K (medium I/O)  
- 128K (large sequential)
- 1M (very large sequential)
  
- **Results**: The script displays the results for each run and the average speed. This should give you an idea of the impacts of various thread-counts (as a synthetic representation of client-counts) and the ZFS ARC caching mechanism. 

**NOTE:** The script's run duration is dependant on the number of threads in your system as well as the number of disks in your system. Small all-flash systems may complete this benchmark in 25 minutes, while larger systems with spinning hardrives may take several hours. The script will not stop other I/O activity on a production system, but will severely limit performance. This benchmark is best run on a system with no other workload. This will give you the best outcome in terms of the accuracy of the data, in addition to not creating angry users.

## Performance Considerations

### ARC Behavior

- ARC hit rate decreases as working set exceeds cache size, which tn-bench intentionally causes.
- Results reflect mixed cache hit/miss scenarios, not neccesarily indicative of a real world workload.

### Resource Requirements
| Resource Type          | Requirement                                  | Notes                                      |
|------------------------|---------------------------------------------|--------------------------------------------|
| Pool Test Space        | 20 GiB per thread                           | Space freed between iterations (v2.0+)     |
| Thread Configurations  | 4 (1, cores÷4, cores÷2, cores)              | For ZFS pool benchmarks                    |
| Default Iterations     | 2 per configuration                         | Configurable 1-100                         |
| Disk Serial Mode       | Low impact                                  | Default, safe for production               |
| Disk Parallel Mode     | Moderate controller load                    | All disks simultaneously                   |
| Disk Seek-Stress Mode  | **High CPU usage** ⚠️                       | Multiple threads per disk, may saturate CPU |

### ⚠️ Resource Allocation Warnings

**SEEK_STRESS Mode:**
- Uses multiple concurrent threads per disk (4 threads default)
- Can saturate all CPU cores
- May cause system instability on heavily loaded systems
- **Not recommended for production systems**
- Only use on dedicated test systems with no other workloads

**PARALLEL Mode:**
- Tests all disks simultaneously
- Heavy load on storage controllers and backplanes
- May impact other I/O operations
- Use with caution on production systems

**SERIAL Mode (Recommended):**
- Tests one disk at a time
- Minimal system impact
- Safe for production use
- Best for baseline performance measurements

### Execution Time
- **Small all-flash systems**: ~10-30 minutes
- **Large HDD arrays**: Several hours or more
- **Progress indicators**: Provided at each stage
- **Status updates**: For each benchmark operation

## Cleanup Options
The script provides interactive prompts to delete test datasets after benchmarking. All temporary files are automatically removed.

```
Delete testing dataset fire/tn-bench? (yes/no): yes
✓ Dataset fire/tn-bench deleted.
```
## UI Enhancement
### The script is now colorized and more human readable.
![a1455ff8f352193cdadd373471d714d42b170ebb](https://github.com/user-attachments/assets/0e938607-b9c4-424b-a780-ad079901f5a5)


## Output Files

`python3 truenas-bench.py [--output /root/my_results.json]`

tn-bench generates three files for each benchmark run:

| File | Suffix | Description |
|------|--------|-------------|
| Results | `.json` | Raw benchmark data with system info, pool benchmarks, and disk benchmarks |
| Analytics | `_analytics.json` | Structured analysis of scaling patterns and per-disk performance |
| Report | `_report.md` | Human-readable markdown report with tables and observations |

### Example
```bash
python3 truenas-bench.py --output results.json
```

Generates:
- `results.json` — Raw benchmark data
- `results_analytics.json` — Scaling analysis and disk comparison
- `results_report.md` — Markdown report for sharing

## Analytics (v2.1+)

tn-bench automatically analyzes benchmark results to identify scaling patterns and performance characteristics:

### What's Analyzed
- **Thread scaling**: How performance changes as thread count increases
- **Optimization points**: Thread count where peak performance occurs
- **Transition deltas**: Speed changes between thread configurations
- **Per-disk variance**: Individual drive performance relative to pool average

### Key Metrics
| Metric | Description |
|--------|-------------|
| Peak Speed | Maximum throughput achieved |
| Optimal Threads | Thread count at peak performance |
| Thread Efficiency | MB/s per thread at peak |
| % of Pool Avg | Disk speed relative to pool mean |

### Sample Analytics Output
```json
{
  "pool_analyses": [{
    "name": "tank",
    "write_scaling": {
      "peak_speed_mbps": 4465.7,
      "optimal_threads": 16,
      "thread_efficiency": 279.1,
      "progression": [...],
      "deltas": [...]
    },
    "read_scaling": { ... },
    "observations": [
      "Speed decreases from 16 to 32 threads"
    ]
  }],
  "disk_comparison": {
    "tank": {
      "pool_average_mbps": 614.5,
      "variance_pct": 0.3,
      "disks": [...]
    }
  }
}
```

The analytics engine uses neutral data presentation — it reports what it observes without making performance judgments. You draw the conclusions.

## Live Telemetry Output (v2.2+)

During benchmark execution, tn-bench collects zpool iostat telemetry and displays detailed per-thread performance statistics in real-time:

### Example Telemetry Summary (M50 TrueNAS)

```
╔══════════════════════════════════════════════════════════╗
║        Zpool Iostat Telemetry Summary for Pool: ice      ║
╚══════════════════════════════════════════════════════════╝
  • Total samples: 1406  |  Steady-state samples: 1287
  • Duration: 1442.23 seconds

────────── Per-Thread-Count Steady-State Analysis ──────────
  WRITE telemetry only (READ excluded due to ZFS ARC cache interference)

  1 Threads (48 samples):
  ┌─ IOPS ────────────────────────────────────────────────────
  │ Mean: 958.4  │ Median: 0.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 4,940.5 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 1,466.3 [High Variance] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 153.0% High Variance │
  └──────────────────────────────────────────────────────────┘
  ┌─ Bandwidth (MB/s) ────────────────────────────────────────
  │ Mean: 307.9  │ Median: 0.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 1,194.2 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 487.5 [Good] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 158.3% High Variance │
  └──────────────────────────────────────────────────────────┘

  10 Threads (100 samples):
  ┌─ IOPS ────────────────────────────────────────────────────
  │ Mean: 6,643.8  │ Median: 6,470.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 11,607.0 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 1,974.5 [High Variance] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 29.7% Variable │
  └──────────────────────────────────────────────────────────┘

  40 Threads (376 samples):
  ┌─ IOPS ────────────────────────────────────────────────────
  │ Mean: 8,003.7  │ Median: 7,855.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 13,925.0 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 2,907.8 [High Variance] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 36.3% High Variance │
  └──────────────────────────────────────────────────────────┘

────────────────────────── Legend ──────────────────────────
  Statistical Measures:
    • Mean:    Average of all samples
    • Median:  Middle value (50th percentile), less affected by outliers
    • P99:     99th percentile - 99% of samples fall below this value
    • Std Dev: Standard deviation - measures spread/consistency
    • CV%:     Coefficient of Variation (std dev / mean × 100)

  CV% Rating (Consistency):
    • Excellent:    < 10%  (highly consistent)
    • Good:         10-20% (good consistency)
    • Variable:     20-30% (some variability)
    • High Variance:  > 30%  (significant inconsistency)
```

### Understanding the Output

**Per-Thread Analysis**: Each thread count configuration shows:
- **IOPS**: Operations per second with consistency ratings
- **Bandwidth (MB/s)**: Throughput with spread analysis
- **Latency (ms)**: Response time statistics (P99-rated by speed thresholds)

**Why READ telemetry is excluded**: ZFS ARC cache artificially inflates read performance numbers, making them misleading. tn-bench reports WRITE telemetry only for accurate pool performance visibility.

## ARC Statistics (v2.2+)

tn-bench v2.2 introduces comprehensive ARC (Adaptive Replacement Cache) telemetry using `arcstat`:

### What's Collected

| Metric | Description |
|--------|-------------|
| ARC Hit % | Percentage of reads served from ARC |
| ARC Size (GiB) | Total ARC memory usage |
| Demand/Prefetch Hit % | Breakdown of hit types |
| MRU/MFU Distribution | Cache list balance |
| L2ARC Hit % | Secondary cache effectiveness (if present) |
| L2ARC Size (GiB) | L2ARC device capacity |
| ZFetch Stats | Prefetch engine performance |

### L2ARC Auto-Detection

- Automatically detects L2ARC via `zpool status`
- On systems **without** L2ARC: L2ARC metrics omitted entirely (no clutter)
- On systems **with** L2ARC: Full L2ARC telemetry collected
- Prevents arcstat crashes on non-L2ARC systems

### Example ARC Summary

```
╔══════════════════════════════════════════════════════════╗
║   ARC Statistics Summary (READ Phase) for Pool: inferno  ║
╚══════════════════════════════════════════════════════════╝
  • Total samples: 487  |  Read-phase samples: 132
  • Duration: 486.23 seconds
  • L2ARC: not present (L2ARC metrics omitted)

──────────── Per-Thread-Count READ ARC Analysis ────────────
  ARC cache performance during READ benchmark phases

  1 Threads (4 samples):
  ┌─ ARC Hit % ───────────────────────────────────────────────
  │ Mean: 99.5% [Excellent] │
  ├──────────────────────────────────────────────────────────┤
  │ Median: 99.9%  │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 0.8 [Excellent] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 0.8% Excellent │
  └──────────────────────────────────────────────────────────┘
  32 Threads (89 samples):
  ┌─ ARC Hit % ───────────────────────────────────────────────
  │ Mean: 57.9% [Poor] │
```

**Rating thresholds:**
- **Excellent**: ≥ 95% (nearly all reads from cache)
- **Good**: 85-95% (majority cached)
- **Variable**: 70-85% (moderate caching)
- **Poor**: < 70% (frequent cache misses)

**Color Coding** (console output):
- **Green**: Excellent ratings
- **Cyan**: Good ratings
- **Yellow**: Variable/Acceptable
- **Red**: High/High Variance

## JSON Schema 

```
{
  "schema_version": "1.0",
  "metadata": {
    "start_timestamp": "2025-03-15T14:30:00",
    "end_timestamp": "2025-03-15T15:15:00",
    "duration_minutes": 45.0,
    "benchmark_config": {
      "selected_pools": ["tank", "backups"],
      "disk_benchmark_run": true,
      "zfs_iterations": 2,
      "disk_iterations": 1
    }
  },
  "system": {
    "os_version": "25.04.1",
    "load_average_1m": 0.85,
    "load_average_5m": 1.2,
    "load_average_15m": 1.1,
    "cpu_model": "Intel Xeon Silver 4210",
    "logical_cores": 40,
    "physical_cores": 20,
    "system_product": "TRUENAS-M50",
    "memory_gib": 251.56
  },
  "pools": [
    {
      "name": "tank",
      "path": "/mnt/tank",
      "status": "ONLINE",
      "vdevs": [
        {"name": "raidz2-0", "type": "RAIDZ2", "disk_count": 8}
      ],
      "benchmark": [
        {
          "threads": 1,
          "write_speeds": [205.57, 209.95],
          "average_write_speed": 207.76,
          "read_speeds": [4775.63, 5029.35],
          "average_read_speed": 4902.49,
          "iterations": 2
        },
        {
          "threads": 10,
          "write_speeds": [1850.32, 1823.45],
          "average_write_speed": 1836.89,
          "read_speeds": [15234.56, 14987.23],
          "average_read_speed": 15110.90,
          "iterations": 2
        }
      ],
      "dwpd": 0.15,
      "total_writes_gib": 640.0
    }
  ],
  "disks": [
    {
      "name": "ada0",
      "model": "ST12000VN0008",
      "serial": "ABC123",
      "zfs_guid": "1234567890",
      "pool": "tank",
      "size_gib": 10999.99,
      "benchmark": {
        "speeds": [210.45],
        "average_speed": 210.45,
        "iterations": 1
      }
    }
  ]
}
```

## Example Output (M50 TrueNAS with v2.2 telemetry)

```

############################################################
#                 tn-bench v2.2 (Modular)                  #
############################################################

TN-Bench is an OpenSource Software Script that uses standard tools to
Benchmark your System and collect various statistical information via
the TrueNAS API.

* TN-Bench will create a Dataset in each of your pools for testing purposes
* that will consume 20 GiB of space for every thread in your system.

! WARNING: This test will make your system EXTREMELY slow during its run.
! WARNING: It is recommended to run this test when no other workloads are running.

* ZFS ARC will impact your results. You can set zfs_arc_max to 1 to prevent ARC caching.
* Setting it back to 0 restores default behavior but requires a system restart.

============================================================
 Confirmation 
============================================================

Would you like to continue? (yes/no): yes

------------------------------------------------------------
|                    System Information                    |
------------------------------------------------------------

Field                 | Value                                     
----------------------+-------------------------------------------
Version               | 25.10.1                                   
Load Average (1m)     | 8.44091796875                             
Load Average (5m)     | 8.38720703125                             
Load Average (15m)    | 9.19482421875                             
Model                 | Intel(R) Xeon(R) Silver 4114 CPU @ 2.20GHz
Cores                 | 40                                        
Physical Cores        | 20                                        
System Product        | TRUENAS-M50-S                             
Physical Memory (GiB) | 251.55                                    

------------------------------------------------------------
|                     Pool Information                     |
------------------------------------------------------------

Field      | Value    
-----------+----------
Name       | fire     
Path       | /mnt/fire
Status     | ONLINE   
VDEV Count | 1        
Disk Count | 4        

VDEV Name  | Type           | Disk Count
-----------+----------------+---------------
raidz1-0    | RAIDZ1         | 4

------------------------------------------------------------
|                     Pool Information                     |
------------------------------------------------------------

Field      | Value   
-----------+---------
Name       | ice     
Path       | /mnt/ice
Status     | ONLINE  
VDEV Count | 5       
Disk Count | 35      

VDEV Name  | Type           | Disk Count
-----------+----------------+---------------
raidz2-0    | RAIDZ2         | 7
raidz2-1    | RAIDZ2         | 7
raidz2-2    | RAIDZ2         | 7
raidz2-3    | RAIDZ2         | 7
raidz2-4    | RAIDZ2         | 7

------------------------------------------------------------
|                     Disk Information                     |
------------------------------------------------------------

* The TrueNAS API returns N/A for the Pool for boot devices and disks not in a pool.
Field      | Value                     
-----------+---------------------------
Name       | sdan                      
Model      | KINGSTON_SA400S37120G     
Serial     | 50026B7784064E49          
ZFS GUID   | None                      
Pool       | N/A                       
Size (GiB) | 111.79                    
-----------+---------------------------
Name       | nvme0n1                   
Model      | INTEL SSDPE2KE016T8       
Serial     | PHLN013100MD1P6AGN        
ZFS GUID   | 17475493647287877073      
Pool       | fire                      
Size (GiB) | 1400.00                   
-----------+---------------------------
Name       | nvme2n1                   
Model      | INTEL SSDPE2KE016T8       
Serial     | PHLN931600FE1P6AGN        
ZFS GUID   | 11275382002255862348      
Pool       | fire                      
Size (GiB) | 1400.00                   
-----------+---------------------------
Name       | nvme3n1                   
Model      | SAMSUNG MZWLL1T6HEHP-00003
Serial     | S3HDNX0KB01220            
ZFS GUID   | 4368323531340162613       
Pool       | fire                      
Size (GiB) | 1399.22                   
-----------+---------------------------
Name       | nvme1n1                   
Model      | SAMSUNG MZWLL1T6HEHP-00003
Serial     | S3HDNX0KB01248            
ZFS GUID   | 3818548647571812337       
Pool       | fire                      
Size (GiB) | 1399.22                   
-----------+---------------------------
Name       | sdo                       
Model      | HUS728T8TAL4204           
Serial     | VAHD4XTL                  
ZFS GUID   | 6447577595542961760       
Pool       | ice                       
Size (GiB) | 7452.04                   
-----------+---------------------------
Name       | sds                       
Model      | HUS728T8TAL4204           
Serial     | VAHE4AJL                  
ZFS GUID   | 11464489017973229028      
Pool       | ice                       
Size (GiB) | 7452.04                   

... (35 total disks)

############################################################
#                      Pool Selection                      #
############################################################

* Available pools:
• 1. fire
• 2. ice
* Options:
• 1. Enter specific pool numbers (comma separated)
• 2. Type 'all' to test all pools
• 3. Type 'none' to skip pool testing

Enter your choice [all]: all

############################################################
#              ZFS Pool Benchmark Iterations               #
############################################################

* How many times should we run each test?
• • Enter any positive integer (1-100, default: 2)
• • Enter 0 to skip this benchmark

Enter iteration count [2]: 1

############################################################
#           Individual Disk Benchmark Iterations           #
############################################################

* How many times should we run each test?
• • Enter any positive integer (1-100, default: 2)
• • Enter 0 to skip this benchmark

Enter iteration count [2]: 0
* Skipping Individual Disk benchmark.

############################################################
#                  DD Benchmark Starting                   #
############################################################

* Using 40 threads for the benchmark.
* ZFS tests will run 1 time(s) per configuration
* Skipping individual disk benchmark

############################################################
#                    Testing Pool: fire                    #
############################################################

* Creating test dataset for pool: fire
✓ Dataset fire/tn-bench created successfully.

============================================================
 Space Verification 
============================================================

* Available space: 2793.50 GiB
* Space required:  800.00 GiB (20 GiB/thread × 40 threads)
* Test iterations: 1 (space freed between iterations)
✓ Sufficient space available - proceeding with benchmarks
* Starting zpool iostat collection for pool 'fire' (interval: 1s)
* Warming up zpool iostat collector (3 samples)...
✓ Zpool iostat collector warmup complete

============================================================
 Testing Pool: fire - Threads: 10 
============================================================

* --- Iteration 1 of 1 ---
* Zpool iostat collector: benchmark phase started
* Zpool iostat collector: segment → 10T-write
* Iteration 1: Writing...
* Iteration 1 write: 2023.22 MB/s
* Zpool iostat collector: segment → 10T-read
* Iteration 1: Reading...
* Iteration 1 read: 6517.87 MB/s
* Space freed after iteration 1

============================================================
 Testing Pool: fire - Threads: 20 
============================================================

* --- Iteration 1 of 1 ---
* Zpool iostat collector: segment → 20T-write
* Iteration 1: Writing...
* Iteration 1 write: 2836.82 MB/s
* Zpool iostat collector: segment → 20T-read
* Iteration 1: Reading...
* Iteration 1 read: 6590.46 MB/s
* Space freed after iteration 1

============================================================
 Testing Pool: fire - Threads: 40 
============================================================

* --- Iteration 1 of 1 ---
* Zpool iostat collector: segment → 40T-write
* Iteration 1: Writing...
* Iteration 1 write: 2813.03 MB/s
* Zpool iostat collector: segment → 40T-read
* Iteration 1: Reading...
* Iteration 1 read: 6628.14 MB/s
* Space freed after iteration 1
* Zpool iostat collector: benchmark phase ended
* Cooling down zpool iostat collector (3 samples)...
✓ Zpool iostat collector cooldown complete
✓ Zpool iostat collection complete: 857 samples

============================================================
 Zpool Iostat Telemetry Summary for Pool: fire 
============================================================


╔══════════════════════════════════════════════════════════╗
║       Zpool Iostat Telemetry Summary for Pool: fire      ║
╚══════════════════════════════════════════════════════════╝
  • Total samples: 857  |  Steady-state samples: 750
  • Duration: 859.54 seconds

────────── Per-Thread-Count Steady-State Analysis ──────────
  WRITE telemetry only (READ excluded due to ZFS ARC cache interference)

  10 Threads (97 samples):
  ┌─ IOPS ────────────────────────────────────────────────────
  │ Mean: 9,851.5  │ Median: 9,880.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 11,424.0 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 889.4 [Variable] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 9.0% Excellent │
  └──────────────────────────────────────────────────────────┘
  ┌─ Bandwidth (MB/s) ────────────────────────────────────────
  │ Mean: 2,667.2  │ Median: 2,680.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 3,030.8 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 248.0 [Good] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 9.3% Excellent │
  └──────────────────────────────────────────────────────────┘
  ┌─ Latency (ms) ────────────────────────────────────────────
  │ Mean: 0.0  │ Median: 0.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 0.0 [Excellent] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 0.0 [Excellent] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 491.5% High Variance │
  └──────────────────────────────────────────────────────────┘

  20 Threads (143 samples):
  ┌─ IOPS ────────────────────────────────────────────────────
  │ Mean: 12,699.0  │ Median: 12,800.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 16,158.0 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 1,454.1 [High Variance] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 11.5%  Good │
  └──────────────────────────────────────────────────────────┘
  ┌─ Bandwidth (MB/s) ────────────────────────────────────────
  │ Mean: 3,698.4  │ Median: 3,830.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 4,055.8 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 368.7 [Good] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 10.0% Excellent │
  └──────────────────────────────────────────────────────────┘
  ┌─ Latency (ms) ────────────────────────────────────────────
  │ Mean: 0.0  │ Median: 0.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 0.0 [Excellent] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 0.0 [Excellent] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 319.0% High Variance │
  └──────────────────────────────────────────────────────────┘

  40 Threads (288 samples):
  ┌─ IOPS ────────────────────────────────────────────────────
  │ Mean: 13,254.2  │ Median: 13,400.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 18,178.0 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 1,991.4 [High Variance] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 15.0%  Good │
  └──────────────────────────────────────────────────────────┘
  ┌─ Bandwidth (MB/s) ────────────────────────────────────────
  │ Mean: 3,680.1  │ Median: 3,860.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 4,050.0 [High] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 410.3 [Good] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 11.2%  Good │
  └──────────────────────────────────────────────────────────┘
  ┌─ Latency (ms) ────────────────────────────────────────────
  │ Mean: 0.0  │ Median: 0.0  │
  ├──────────────────────────────────────────────────────────┤
  │ P99: 0.3 [Excellent] │
  ├──────────────────────────────────────────────────────────┤
  │ Std Dev: 0.0 [Excellent] │
  ├──────────────────────────────────────────────────────────┤
  │ CV%: 449.0% High Variance │
  └──────────────────────────────────────────────────────────┘

────────────────────────── Legend ──────────────────────────
  Statistical Measures:
    • Mean:    Average of all samples
    • Median:  Middle value (50th percentile), less affected by outliers
    • P99:     99th percentile - 99% of samples fall below this value
    • Std Dev: Standard deviation - measures spread/consistency
    • CV%:     Coefficient of Variation (std dev / mean × 100)

  CV% Rating (Consistency):
    • Excellent:    < 10%  (highly consistent)
    • Good:         10-20% (good consistency)
    • Variable:     20-30% (some variability)
    • High Variance:  > 30%  (significant inconsistency)

  P99 Latency Rating (Lower is better):
    • Excellent:    < 10ms   (very fast)
    • Good:         < 50ms   (acceptable)
    • Acceptable:  < 100ms  (may impact workload)
    • High:          > 100ms  (significant latency)

  Std Dev Rating (Consistency - Lower is better):
    • Excellent:    Low spread    (very consistent)
    • Good:         Moderate      (acceptable spread)
    • Variable:     Noticeable    (some spread)
    • High Variance:  Wide spread   (inconsistent)

============================================================
 Pool Write Summary 
============================================================

* Total data written: 1420.00 GiB
* Pool capacity: 5584.00 GiB
* Benchmark duration: 867.60 seconds
* Drive Writes Per Day (DWPD): 25.32
* Cleaning up any remaining test files...

############################################################
#                    Benchmark Complete                    #
############################################################

✓ Total benchmark time: 16.01 minutes
 
```

## Unattended Mode (v2.3+)

tn-bench v2.3 adds full support for unattended/automated operation. All interactive prompts can be bypassed using CLI arguments, enabling batch testing, CI/CD integration, and scripted runs.

### CLI Options

| Argument | Description | Values | Required in Unattended |
|----------|-------------|--------|------------------------|
| `--unattended`, `--auto` | Enable unattended mode (skip all prompts) | `true` when present | No (but required to bypass prompts) |
| `--output` | Output JSON file path | Path string | No (default: `./tn_bench_results.json`) |
| `--pools` | Pool selection | `'all'`, `'none'`, or comma-separated names (e.g., `'fire,ice'`) | **Yes** |
| `--zfs-iterations` | ZFS pool benchmark iterations | Integer 0-100 (0 = skip) | **Yes** |
| `--pool-block-size` | Pool benchmark block size | `16K`, `32K`, `64K`, `128K`, `256K`, `512K`, `1M`, `2M`, `4M`, `8M`, `16M` | No (default: `1M`) |
| `--disk-iterations` | Disk benchmark iterations | Integer 0-100 (0 = skip) | **Yes** |
| `--disk-modes` | Disk test modes, comma-separated | `serial`, `parallel`, `seek_stress` | No (default: `serial`) |
| `--disk-block-size` | Disk benchmark block size | `4K`, `32K`, `128K`, `1M` | No (default: `1M`) |
| `--seek-threads` | Threads per disk for seek_stress mode | Integer 1-32 | No (default: `4`) |
| `--confirm` | Auto-confirm safety prompt | `true` when present | **Yes** |
| `--cleanup` | Auto-answer dataset cleanup | `yes` or `no` | No (default: `yes`) |

### Preset Examples

#### All pools, no disks
```bash
python3 truenas-bench.py --unattended --pools all --zfs-iterations 2 --disk-iterations 0 --confirm
```

#### All disks, no pools
```bash
python3 truenas-bench.py --unattended --pools none --zfs-iterations 0 --disk-iterations 2 --disk-modes serial --confirm
```

#### Burn-in mode
```bash
python3 truenas-bench.py --unattended --pools all --zfs-iterations 5 --disk-iterations 3 --disk-modes serial,parallel --confirm
```

#### Specific pools with custom block sizes
```bash
python3 truenas-bench.py --unattended --pools fire,ice --zfs-iterations 2 --pool-block-size 128K --disk-iterations 1 --disk-block-size 1M --disk-modes serial --confirm
```

#### Seek-stress test with cleanup disabled
```bash
python3 truenas-bench.py --unattended --pools none --zfs-iterations 0 --disk-iterations 1 --disk-modes seek_stress --seek-threads 8 --cleanup no --confirm
```

### Validation Rules

When `--unattended` is used:
1. **`--confirm` is required** — safety acknowledgment
2. **`--pools` is required** — specify which pools to test
3. **`--zfs-iterations` is required** — even if set to 0 (skip)
4. **`--disk-iterations` is required** — even if set to 0 (skip)
5. **All other arguments have sensible defaults** matching interactive mode
6. **Missing required arguments trigger a helpful error** with example usage
7. **Dataset cleanup defaults to `yes`** — temp datasets are deleted unless `--cleanup no`

### Sample Output in Unattended Mode
```
############################################################
#                 tn-bench v2.3 (Unattended)               #
############################################################

* Mode: UNATTENDED (all prompts skipped)
* Unattended: Selected pools: fire, ice
* Unattended: ZFS pool iterations: 2
* Unattended: Pool block size: 128K
* Unattended: Disk iterations: 1
* Unattended: Disk test modes: serial
* Unattended: Disk block size: 1M
* Unattended: Dataset cleanup: yes

...
```

### Compatibility Notes

- **Interactive mode remains default** — no breaking changes
- **All existing functionality preserved** — unattended is additive
- **Argument validation mirrors interactive bounds** — same 0-100 ranges, same block size options
- **Error messages guide users** — show missing arguments with examples
- **Default cleanup behavior** — datasets auto-deleted in unattended (configurable)

## Batch/Matrix Config Mode (v2.3+)

For automated sequential runs with different configurations — such as testing all block sizes on the same pool, comparing multiple pools with the same workload, or running a regression test suite — use `--config` with a JSON or YAML configuration file.

### Quick Start

```bash
python3 truenas-bench.py --config batch_block_size_matrix.json --confirm
```

### CLI Argument

| Argument | Description |
|----------|-------------|
| `--config <path>` | Path to JSON or YAML batch config file |
| `--confirm` | Required safety confirmation |
| `--output` | Base path for output files (default: `./tn_bench_results.json`) |

`--config` is mutually exclusive with `--unattended` individual arguments. When `--config` is used, all run parameters come from the config file.

### Config File Schema

Config files have three top-level sections:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `description` | string | No | Human-readable description of this batch |
| `continue_on_error` | bool | No | If true, continue to next run on failure (default: false) |
| `global` | object | No | Default settings applied to all runs |
| `runs` | array | **Yes** | List of individual benchmark runs |

#### Global Settings

The `global` object sets defaults for all runs. Any setting in a run overrides the global value.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pools` | list/string | `["all"]` | Pool selection: list of names, `["all"]`, or `["none"]` |
| `zfs_iterations` | int | `2` | ZFS benchmark iterations (0-100, 0 = skip) |
| `pool_block_size` | string | `"1M"` | Block size: 4K, 16K, 32K, 64K, 128K, 256K, 512K, 1M, 2M, 4M, 8M, 16M |
| `disk_iterations` | int | `0` | Disk benchmark iterations (0-100, 0 = skip) |
| `disk_modes` | list | `["serial"]` | Disk test modes: serial, parallel, seek_stress |
| `disk_block_size` | string | `"1M"` | Disk block size: 4K, 32K, 128K, 1M |
| `seek_threads` | int | `4` | Threads per disk for seek_stress (1-32) |
| `cleanup` | bool | `true` | Delete test datasets after each run |
| `verify_cleanup` | bool | `true` | Verify dataset deletion after cleanup |
| `retry_cleanup` | int | `3` | Max cleanup retry attempts |
| `force_cleanup` | bool | `false` | Use force delete on cleanup |

#### Run Settings

Each run in the `runs` array has:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | **Yes** | Unique name for this run (used in filenames) |
| *(any global key)* | *(same)* | No | Override any global setting for this run |

### Config File Examples

#### JSON: Block Size Matrix

```json
{
  "description": "Block size matrix test on inferno pool",
  "continue_on_error": true,
  "global": {
    "pools": ["inferno"],
    "cleanup": true,
    "verify_cleanup": true,
    "retry_cleanup": 3,
    "disk_iterations": 0
  },
  "runs": [
    {
      "name": "4K-block-test",
      "zfs_iterations": 2,
      "pool_block_size": "4K"
    },
    {
      "name": "32K-block-test",
      "zfs_iterations": 2,
      "pool_block_size": "32K"
    },
    {
      "name": "128K-block-test",
      "zfs_iterations": 2,
      "pool_block_size": "128K"
    },
    {
      "name": "1M-block-test",
      "zfs_iterations": 2,
      "pool_block_size": "1M"
    }
  ]
}
```

#### YAML: Block Size Matrix

```yaml
description: "Block size matrix test on inferno pool"
continue_on_error: true

global:
  pools:
    - inferno
  cleanup: true
  verify_cleanup: true
  retry_cleanup: 3
  disk_iterations: 0

runs:
  - name: 4K-block-test
    zfs_iterations: 2
    pool_block_size: "4K"

  - name: 32K-block-test
    zfs_iterations: 2
    pool_block_size: "32K"

  - name: 128K-block-test
    zfs_iterations: 2
    pool_block_size: "128K"

  - name: 1M-block-test
    zfs_iterations: 2
    pool_block_size: "1M"
```

#### Iteration Scaling Test

```json
{
  "description": "Measure variance reduction with more iterations",
  "continue_on_error": true,
  "global": {
    "pools": ["all"],
    "cleanup": true,
    "pool_block_size": "1M",
    "disk_iterations": 0
  },
  "runs": [
    { "name": "1-iteration", "zfs_iterations": 1 },
    { "name": "2-iterations", "zfs_iterations": 2 },
    { "name": "5-iterations", "zfs_iterations": 5 },
    { "name": "10-iterations", "zfs_iterations": 10 }
  ]
}
```

#### Multi-Pool Comparison

```json
{
  "description": "Same config on different pools",
  "continue_on_error": true,
  "global": {
    "cleanup": true,
    "zfs_iterations": 3,
    "pool_block_size": "1M",
    "disk_iterations": 0
  },
  "runs": [
    { "name": "fire-pool", "pools": ["fire"] },
    { "name": "ice-pool", "pools": ["ice"] },
    { "name": "inferno-pool", "pools": ["inferno"] }
  ]
}
```

#### Regression Test Suite

```json
{
  "description": "Known good configurations for periodic validation",
  "continue_on_error": false,
  "global": {
    "cleanup": true,
    "verify_cleanup": true,
    "retry_cleanup": 5,
    "force_cleanup": true
  },
  "runs": [
    {
      "name": "baseline-1M-zfs",
      "pools": ["all"],
      "zfs_iterations": 2,
      "pool_block_size": "1M",
      "disk_iterations": 0
    },
    {
      "name": "baseline-disk-serial",
      "pools": ["none"],
      "zfs_iterations": 0,
      "disk_iterations": 2,
      "disk_modes": ["serial"],
      "disk_block_size": "1M"
    }
  ]
}
```

### Output Files

Batch mode generates individual results per run plus an aggregate summary:

| File | Description |
|------|-------------|
| `tn_bench_results_run1_4K-block-test.json` | Raw results for run 1 |
| `tn_bench_results_run1_4K-block-test_analytics.json` | Analytics for run 1 |
| `tn_bench_results_run1_4K-block-test_report.md` | Report for run 1 |
| `tn_bench_results_run2_32K-block-test.json` | Raw results for run 2 |
| ... | *(same pattern for each run)* |
| `tn_bench_results_batch_summary.json` | **Aggregate summary with comparison** |

### Batch Summary Schema

```json
{
  "description": "Block size matrix test on inferno pool",
  "config_file": "/root/batch_block_size_matrix.json",
  "start_time": "2025-02-08T14:30:00",
  "end_time": "2025-02-08T16:45:00",
  "total_duration_minutes": 135.0,
  "total_runs": 4,
  "successful_runs": 4,
  "failed_runs": 0,
  "system_info": {
    "cpu_model": "Intel Xeon Silver 4114",
    "logical_cores": 40,
    "memory_gib": 251.55
  },
  "runs": [
    {
      "index": 1,
      "name": "4K-block-test",
      "status": "success",
      "config": {
        "pools": ["inferno"],
        "zfs_iterations": 2,
        "pool_block_size": "4K"
      },
      "pool_metrics": {
        "inferno": {
          "peak_write_mbps": 245.3,
          "peak_write_threads": 40,
          "peak_read_mbps": 1234.5,
          "peak_read_threads": 20,
          "dwpd": 5.67,
          "total_writes_gib": 640.0,
          "duration_seconds": 1842.5
        }
      },
      "output_file": "/root/tn_bench_results_run1_4K-block-test.json",
      "duration_seconds": 1850.3
    }
  ]
}
```

### Robust Dataset Cleanup

Batch mode includes hardened dataset cleanup between runs:

1. **Pre-run safety check** — if a stale `tn-bench` dataset exists before creating a new one, it's automatically cleaned up first
2. **Post-run cleanup** — dataset is deleted after each run completes
3. **Verification** — after deletion, the API is queried to confirm the dataset no longer exists
4. **Retry logic** — configurable retries (default 3) with automatic escalation to force delete
5. **Force delete** — `force_cleanup: true` uses forced deletion from the first attempt
6. **Non-blocking** — if cleanup ultimately fails after all retries, a warning is logged and the batch continues to the next run

### Sample Batch Output

```
############################################################
#                 tn-bench v2.3 (Modular)                  #
############################################################

============================================================
 Batch Config Mode
============================================================

* Description: Block size matrix test on inferno pool
* Total runs: 4
* Continue on error: true
• Run 1: 4K-block-test — pools=['inferno'], block_size=4K, zfs_iter=2, disk_iter=0
• Run 2: 32K-block-test — pools=['inferno'], block_size=32K, zfs_iter=2, disk_iter=0
• Run 3: 128K-block-test — pools=['inferno'], block_size=128K, zfs_iter=2, disk_iter=0
• Run 4: 1M-block-test — pools=['inferno'], block_size=1M, zfs_iter=2, disk_iter=0

✓ Batch configuration validated — starting runs.

############################################################
#              Run 1 of 4: 4K-block-test                   #
############################################################

* Pools: inferno
* ZFS iterations: 2, Pool block size: 4k
...
✓ Run 1 (4K-block-test) completed successfully.

############################################################
#              Run 2 of 4: 32K-block-test                  #
############################################################

...

############################################################
#                Batch Results Comparison                   #
############################################################

============================================================
 Pool: inferno
============================================================

Run                            Status     Write MB/s   Read MB/s    DWPD     Duration
----------------------------------------------------------------------------------------------
4K-block-test                  success    245.3        1234.5       5.67     1843s
32K-block-test                 success    1023.7       3456.2       12.34    923s
128K-block-test                success    2345.1       5678.3       18.91    612s
1M-block-test                  success    3456.8       6789.4       25.32    487s

############################################################
#                     Batch Complete                        #
############################################################

✓ Total batch time: 64.42 minutes
* Successful: 4 / 4
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or fixes.

## License

This project is licensed under the GPLv3 License - see the [LICENSE](LICENSE) file for details.
