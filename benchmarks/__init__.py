"""
tn-bench Benchmarks Module

Available benchmarks:
- ZFSPoolBenchmark: ZFS pool sequential write/read with zpool iostat telemetry
- EnhancedDiskBenchmark: Individual disk benchmark with serial, parallel, and seek-stress modes

Architecture note:
  The original DiskBenchmark (disk_raw.py) was removed in the 2.1 audit.
  EnhancedDiskBenchmark in serial mode with block_size="1" (4K) is a strict
  superset of the old DiskBenchmark functionality.
"""

from benchmarks.base import BenchmarkBase
from benchmarks.zfs_pool import ZFSPoolBenchmark, POOL_BLOCK_SIZES
from benchmarks.disk_enhanced import EnhancedDiskBenchmark, BLOCK_SIZES

__all__ = ['BenchmarkBase', 'ZFSPoolBenchmark', 'POOL_BLOCK_SIZES', 'EnhancedDiskBenchmark', 'BLOCK_SIZES']
