# TN-Bench 2.0 - Modular Architecture

## Overview
Complete refactor of TN-Bench into a modular architecture while maintaining 100% backward compatibility with the existing user interface.

## Directory Structure

```
tn-bench/
├── truenas-bench.py          # Main UI/coordinator (refactored)
├── core/                     # Core functionality modules
│   ├── __init__.py          # System info, pool info, disk info
│   ├── dataset.py           # Dataset create/delete/validate
│   └── results.py           # JSON output formatting
├── benchmarks/              # Benchmark implementations
│   ├── __init__.py          # Exports benchmark classes
│   ├── base.py              # Abstract base class
│   ├── zfs_pool.py          # ZFS pool write/read benchmark
│   └── disk_raw.py          # Individual disk read benchmark
└── utils/                   # Common utilities
    └── __init__.py          # Color, formatting, print helpers
```

## Module Responsibilities

### `utils/` - Common Utilities
- ANSI color codes and text formatting
- Print helpers (header, subheader, section, info, success, warning, error, bullet)
- `color_text()` for conditional terminal coloring

### `core/` - Core Functionality
- **`__init__.py`**: System/pool/disk information collection via TrueNAS API
- **`dataset.py`**: Dataset lifecycle management (create, delete, space validation)
- **`results.py`**: JSON output transformation and saving

### `benchmarks/` - Benchmark Implementations
- **`base.py`**: Abstract `BenchmarkBase` class defining the interface:
  - `name`, `description` class attributes
  - `validate()` - Check prerequisites
  - `run(config)` - Execute benchmark
  - `space_required_gib` - Space calculation property
- **`zfs_pool.py`**: `ZFSPoolBenchmark` class
  - Sequential write/read with varying thread counts
  - Thread counts: 1, cores/4, cores/2, cores
  - 20 GiB per thread
- **`disk_raw.py`**: `DiskBenchmark` class
  - 4K sequential read on individual disks
  - Read size = min(system RAM, disk size)

### `truenas-bench.py` - Main Coordinator
- User interface and flow control (unchanged from v1.x)
- Delegates to modules for all operations
- Maintains identical command-line interface
- Same interactive prompts and output format

## Key Benefits

1. **Maintainability**: Each component is isolated and testable
2. **Extensibility**: New benchmarks can be added by:
   - Creating a new file in `benchmarks/`
   - Inheriting from `BenchmarkBase`
   - Importing and using in main script
3. **Clarity**: Separation of concerns makes code easier to understand
4. **Testing**: Individual modules can be unit tested
5. **Reusability**: Core utilities can be used by future benchmarks

## Backward Compatibility

✅ **100% Compatible**: No changes to:
- Command-line arguments (`--output`)
- Interactive prompts and flow
- Console output formatting
- JSON output schema
- Benchmark behavior and calculations

## Adding New Benchmarks

To add a new benchmark:

1. Create a new file in `benchmarks/` (e.g., `my_benchmark.py`)
2. Inherit from `BenchmarkBase`:

```python
from benchmarks.base import BenchmarkBase
from utils import print_info, print_success

class MyBenchmark(BenchmarkBase):
    name = "my_benchmark"
    description = "Description of my benchmark"
    
    def __init__(self, config):
        self.config = config
    
    def validate(self) -> bool:
        # Check prerequisites
        return True
    
    @property
    def space_required_gib(self) -> int:
        return 0
    
    def run(self, config: dict = None) -> dict:
        # Run benchmark
        print_info("Running my benchmark...")
        return {"results": "data"}
```

3. Export in `benchmarks/__init__.py`:
```python
from benchmarks.my_benchmark import MyBenchmark
__all__ = ['BenchmarkBase', 'ZFSPoolBenchmark', 'DiskBenchmark', 'MyBenchmark']
```

4. Use in `truenas-bench.py`:
```python
from benchmarks import MyBenchmark

# In main():
my_bench = MyBenchmark(config)
results = my_bench.run()
```

## Version History

- **v1.11**: Monolithic single-file script
- **v2.0**: Modular architecture (this version)
