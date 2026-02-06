"""
TN-Bench Benchmarks Module

Available benchmarks:
- ZFSPoolBenchmark: ZFS pool sequential write/read
- DiskBenchmark: Individual disk 4K sequential read
"""

from benchmarks.base import BenchmarkBase
from benchmarks.zfs_pool import ZFSPoolBenchmark
from benchmarks.disk_raw import DiskBenchmark

__all__ = ['BenchmarkBase', 'ZFSPoolBenchmark', 'DiskBenchmark']
