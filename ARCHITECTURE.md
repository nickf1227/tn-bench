# tn-bench 2.1 - Modular Architecture

## Overview
tn-bench uses a modular architecture with clean separation between UI, core functionality, and benchmark implementations. Version 2.1 adds analytics and zpool iostat telemetry collection.

## Directory Structure

```
tn-bench/
├── truenas-bench.py              # Main UI/coordinator
├── core/                         # Core functionality modules
│   ├── __init__.py              # System/pool/disk info, zpool iostat exports
│   ├── dataset.py               # Dataset create/delete/validate
│   ├── results.py               # JSON output formatting
│   ├── analytics.py             # Neutral scaling analysis (v2.1)
│   ├── report_generator.py      # Markdown report generation (v2.1)
│   └── zpool_iostat_collector.py  # ZFS pool iostat telemetry (v2.1)
├── benchmarks/                  # Benchmark implementations
│   ├── __init__.py              # Exports benchmark classes
│   ├── base.py                  # Abstract BenchmarkBase class
│   ├── zfs_pool.py              # ZFS pool write/read benchmark
│   ├── disk_raw.py              # Individual disk read benchmark
│   └── disk_enhanced.py         # Enhanced disk benchmark with modes (v2.1)
├── utils/                       # Common utilities
│   └── __init__.py              # Color, formatting, print helpers
└── test_zpool_iostat_collector.py  # Tests for zpool iostat collector
```

## Module Responsibilities

### `utils/` - Common Utilities
- ANSI color codes and text formatting
- Print helpers (header, subheader, section, info, success, warning, error, bullet)
- `color_text()` for conditional terminal coloring

### `core/` - Core Functionality
- **`__init__.py`**: System/pool/disk information collection via TrueNAS API; exports zpool iostat collector classes
- **`dataset.py`**: Dataset lifecycle management (create, delete, space validation)
- **`results.py`**: JSON output transformation and saving
- **`analytics.py`**: Neutral scaling analysis with dataclasses - runs post-benchmark for reports
- **`report_generator.py`**: Markdown report generation from analytics data
- **`zpool_iostat_collector.py`**: Background collection of `zpool iostat` telemetry during benchmarks

### `benchmarks/` - Benchmark Implementations
- **`base.py`**: Abstract `BenchmarkBase` class defining the interface
- **`zfs_pool.py`**: `ZFSPoolBenchmark` - Sequential write/read with zpool iostat integration
- **`disk_raw.py`**: `DiskBenchmark` - Individual disk read testing
- **`disk_enhanced.py`**: `EnhancedDiskBenchmark` - Multiple test modes (serial/parallel/seek_stress)

### `truenas-bench.py` - Main Coordinator
- User interface and flow control
- Delegates to modules for all operations
- Runs analytics and generates reports post-benchmark

## Key Components

### ZPool Iostat Collector (v2.1)

Background telemetry collection during pool benchmarks:

```python
from core.zpool_iostat_collector import ZpoolIostatCollector

collector = ZpoolIostatCollector(pool_name="tank", interval=1)
collector.start(warmup_iterations=3)
# ... benchmark runs ...
telemetry = collector.stop(cooldown_iterations=3)
```

Features:
- Non-blocking background collection via subprocess
- Warmup and cooldown periods
- Extended latency statistics (with `-l` flag)
- Automatic process cleanup

### Analytics Engine (v2.1)

Neutral data presentation using dataclasses:

```python
from core.analytics import ResultAnalyzer

analyzer = ResultAnalyzer(results_dict)
analysis = analyzer.analyze()  # Returns SystemAnalysis
```

Outputs:
- Pool scaling analysis (write/read progression)
- Disk comparison across pools
- Neutral observations (no grades/opinions)

### Report Generator (v2.1)

Markdown report from analytics:

```python
from core.report_generator import generate_markdown_report

report = generate_markdown_report(analysis_dict, output_path)
```

## Analysis Pipeline

Post-benchmark analysis is handled by the **analytics engine** (`analytics.py`):

- Runs after benchmark completion via `ResultAnalyzer`
- Neutral data presentation (no grades or judgments)
- Generates separate `_analytics.json` and `_report.md` files
- Focuses on scaling patterns, deltas, and observations

The analytics data is kept separate from the main results JSON to maintain clean separation between raw benchmark data and derived analysis.

## Adding New Benchmarks

1. Create a new file in `benchmarks/` (e.g., `my_benchmark.py`)
2. Inherit from `BenchmarkBase`:

```python
from benchmarks.base import BenchmarkBase

class MyBenchmark(BenchmarkBase):
    name = "my_benchmark"
    description = "Description"
    
    def validate(self) -> bool:
        return True
    
    @property
    def space_required_gib(self) -> int:
        return 0
    
    def run(self, config: dict = None) -> dict:
        return {"results": "data"}
```

3. Export in `benchmarks/__init__.py`
4. Use in `truenas-bench.py`

## Version History

- **v1.11**: Monolithic single-file script
- **v2.0**: Modular architecture, space optimization
- **v2.1**: Analytics engine, zpool iostat collection, enhanced disk benchmark
