"""
ZFS Pool benchmark - sequential write/read across varying thread counts.
Space-optimized version: cleans up test files between iterations to reduce space requirements.
Integrates with zpool iostat collector for telemetry during benchmark runs.
"""

import subprocess
import threading
import time
import os
from benchmarks.base import BenchmarkBase
from utils import (
    print_info, print_success, print_section, print_header,
    print_subheader, print_bullet, color_text
)


def run_dd_command(command):
    """Execute a dd command in a subprocess."""
    subprocess.run(command, shell=True)


def cleanup_test_files(dataset_path, file_prefix, num_threads):
    """Clean up test files for a specific thread count."""
    for i in range(num_threads):
        file_path = f"{dataset_path}/{file_prefix}{i}.dat"
        if os.path.exists(file_path):
            os.remove(file_path)


def run_single_iteration(threads, bytes_per_thread, block_size, file_prefix, dataset_path, iteration_num,
                         on_segment_change=None):
    """
    Run a single write/read iteration and cleanup.
    
    Args:
        on_segment_change: Optional callback(label: str) invoked before each
                          write/read phase starts so the telemetry collector can
                          label the workload segment.
    
    Returns:
        tuple: (write_speed, read_speed, bytes_written)
    """
    # Write phase
    if on_segment_change:
        on_segment_change(f"{threads}T-write")
    print_info(f"Iteration {iteration_num}: Writing...")
    start_time = time.time()
    
    threads_list = []
    for i in range(threads):
        command = f"dd if=/dev/urandom of={dataset_path}/{file_prefix}{i}.dat bs={block_size} count={bytes_per_thread} status=none"
        thread = threading.Thread(target=run_dd_command, args=(command,))
        thread.start()
        threads_list.append(thread)
    
    for thread in threads_list:
        thread.join()
    
    end_time = time.time()
    total_time_taken = end_time - start_time
    
    block_size_bytes = 1024 * 1024  # 1M
    bytes_written = threads * bytes_per_thread * block_size_bytes
    write_speed = bytes_written / total_time_taken / (1024 * 1024)
    
    print_info(f"Iteration {iteration_num} write: {color_text(f'{write_speed:.2f} MB/s', 'YELLOW')}")
    
    # Read phase
    if on_segment_change:
        on_segment_change(f"{threads}T-read")
    print_info(f"Iteration {iteration_num}: Reading...")
    start_time = time.time()
    
    threads_list = []
    for i in range(threads):
        command = f"dd if={dataset_path}/{file_prefix}{i}.dat of=/dev/null bs={block_size} count={bytes_per_thread} status=none"
        thread = threading.Thread(target=run_dd_command, args=(command,))
        thread.start()
        threads_list.append(thread)
    
    for thread in threads_list:
        thread.join()
    
    end_time = time.time()
    total_time_taken = end_time - start_time
    
    read_speed = bytes_written / total_time_taken / (1024 * 1024)
    
    print_info(f"Iteration {iteration_num} read: {color_text(f'{read_speed:.2f} MB/s', 'YELLOW')}")
    
    # Cleanup immediately after read to free space
    cleanup_test_files(dataset_path, file_prefix, threads)
    
    return write_speed, read_speed, bytes_written


class ZFSPoolBenchmark(BenchmarkBase):
    """ZFS Pool sequential write/read benchmark with optional zpool iostat telemetry collection."""
    
    name = "zfs_pool"
    description = "ZFS Pool sequential write/read benchmark with varying thread counts and zpool iostat telemetry"
    
    def __init__(
        self,
        pool_name,
        cores,
        dataset_path,
        iterations=2,
        collect_zpool_iostat=True,
        zpool_iostat_interval=1,
        zpool_iostat_warmup=3,
        zpool_iostat_cooldown=3
    ):
        self.pool_name = pool_name
        self.cores = cores
        self.dataset_path = dataset_path
        self.iterations = iterations
        self.bytes_per_thread = 20480  # 20 GiB per thread
        self.block_size = "1M"
        self.file_prefix = "file_"
        
        # Zpool iostat collection settings
        self.collect_zpool_iostat = collect_zpool_iostat
        self.zpool_iostat_interval = zpool_iostat_interval
        self.zpool_iostat_warmup = zpool_iostat_warmup
        self.zpool_iostat_cooldown = zpool_iostat_cooldown
        self.zpool_iostat_collector = None
        self.zpool_iostat_telemetry = None
    
    def validate(self) -> bool:
        """Check if dataset path exists and is writable."""
        return os.path.exists(self.dataset_path) and os.access(self.dataset_path, os.W_OK)
    
    @property
    def space_required_gib(self) -> int:
        """
        Calculate space required: 20 GiB per thread (single iteration).
        Space is freed between iterations, so we only need space for one iteration.
        """
        max_threads = self.cores
        return 20 * max_threads  # Only need space for one iteration at a time
    
    def _run_benchmark_with_zpool_iostat(self):
        """
        Run the benchmark with zpool iostat collection.
        
        Returns:
            dict: Benchmark results with zpool iostat telemetry
        """
        # Import here to avoid circular imports and allow running without collector
        try:
            from core.zpool_iostat_collector import (
                ZpoolIostatCollector, calculate_zpool_iostat_summary
            )
        except ImportError:
            print_info("Zpool iostat collector not available, running without telemetry")
            return self._run_benchmark_without_zpool_iostat()
        
        escaped_pool_name = self.pool_name.replace(" ", "\\ ")
        thread_counts = [1, self.cores // 4, self.cores // 2, self.cores]
        results = []
        total_bytes_written = 0
        
        # Initialize and start the collector
        self.zpool_iostat_collector = ZpoolIostatCollector(
            pool_name=self.pool_name,
            interval=self.zpool_iostat_interval,
            extended_stats=True
        )
        
        collector_started = self.zpool_iostat_collector.start(
            warmup_iterations=self.zpool_iostat_warmup
        )
        
        if not collector_started:
            print_info("Failed to start zpool iostat collector, continuing without telemetry")
            self.zpool_iostat_collector = None
            return self._run_benchmark_without_zpool_iostat()
        
        # Build a segment-change callback so iostat samples get labelled
        def _on_segment_change(label: str):
            if self.zpool_iostat_collector:
                self.zpool_iostat_collector.signal_segment_change(label)

        try:
            # Run the benchmark
            for threads in thread_counts:
                print_section(f"Testing Pool: {escaped_pool_name} - Threads: {threads}")
                
                write_speeds = []
                read_speeds = []
                bytes_written_for_config = 0
                
                for iteration in range(1, self.iterations + 1):
                    print_info(f"--- Iteration {iteration} of {self.iterations} ---")
                    
                    # Signal benchmark start on first iteration of first thread count
                    if iteration == 1 and threads == thread_counts[0] and self.zpool_iostat_collector:
                        self.zpool_iostat_collector.signal_benchmark_start()
                    
                    write_speed, read_speed, bytes_written = run_single_iteration(
                        threads, self.bytes_per_thread, self.block_size,
                        self.file_prefix, self.dataset_path, iteration,
                        on_segment_change=_on_segment_change,
                    )
                    write_speeds.append(write_speed)
                    read_speeds.append(read_speed)
                    bytes_written_for_config += bytes_written
                    total_bytes_written += bytes_written
                    print_info(f"Space freed after iteration {iteration}")
                    
                    # Signal benchmark end on last iteration of last thread count
                    if iteration == self.iterations and threads == thread_counts[-1] and self.zpool_iostat_collector:
                        self.zpool_iostat_collector.signal_benchmark_end()
                
                average_write_speed = sum(write_speeds) / len(write_speeds) if write_speeds else 0
                average_read_speed = sum(read_speeds) / len(read_speeds) if read_speeds else 0
                
                results.append({
                    "threads": threads,
                    "write_speeds": write_speeds,
                    "average_write_speed": average_write_speed,
                    "read_speeds": read_speeds,
                    "average_read_speed": average_read_speed,
                    "iterations": self.iterations,
                    "bytes_written": bytes_written_for_config
                })
        
        except KeyboardInterrupt:
            print_info("\nBenchmark interrupted by user")
            raise
        finally:
            # Stop collector with cooldown
            if self.zpool_iostat_collector:
                self.zpool_iostat_telemetry = self.zpool_iostat_collector.stop(
                    cooldown_iterations=self.zpool_iostat_cooldown
                )
        
        # Print zpool iostat summary if available
        if self.zpool_iostat_telemetry:
            self._print_inline_telemetry_summary(escaped_pool_name)
        
        return {
            "benchmark_results": results,
            "total_bytes_written": total_bytes_written,
            "zpool_iostat_telemetry": self.zpool_iostat_telemetry.to_dict(sample_interval=5) if self.zpool_iostat_telemetry else None
        }
    
    def _run_benchmark_without_zpool_iostat(self):
        """
        Run the benchmark without zpool iostat collection (original behavior).
        
        Returns:
            dict: Benchmark results
        """
        escaped_pool_name = self.pool_name.replace(" ", "\\ ")
        thread_counts = [1, self.cores // 4, self.cores // 2, self.cores]
        results = []
        total_bytes_written = 0
        
        for threads in thread_counts:
            print_section(f"Testing Pool: {escaped_pool_name} - Threads: {threads}")
            
            write_speeds = []
            read_speeds = []
            bytes_written_for_config = 0
            
            # Run iterations sequentially with cleanup between each
            for iteration in range(1, self.iterations + 1):
                print_info(f"--- Iteration {iteration} of {self.iterations} ---")
                write_speed, read_speed, bytes_written = run_single_iteration(
                    threads, self.bytes_per_thread, self.block_size,
                    self.file_prefix, self.dataset_path, iteration
                )
                write_speeds.append(write_speed)
                read_speeds.append(read_speed)
                bytes_written_for_config += bytes_written
                total_bytes_written += bytes_written
                print_info(f"Space freed after iteration {iteration}")
            
            average_write_speed = sum(write_speeds) / len(write_speeds) if write_speeds else 0
            average_read_speed = sum(read_speeds) / len(read_speeds) if read_speeds else 0
            
            results.append({
                "threads": threads,
                "write_speeds": write_speeds,
                "average_write_speed": average_write_speed,
                "read_speeds": read_speeds,
                "average_read_speed": average_read_speed,
                "iterations": self.iterations,
                "bytes_written": bytes_written_for_config
            })
        
        return {
            "benchmark_results": results,
            "total_bytes_written": total_bytes_written
        }
    
    def run(self, config: dict = None) -> dict:
        """
        Run the ZFS pool benchmark across four thread-count configurations.
        
        If collect_zpool_iostat is True (default), collects zpool iostat telemetry
        during the benchmark with warmup and cooldown periods.
        
        Args:
            config: Optional configuration dictionary
            
        Returns:
            dict: Results containing thread counts, speeds, metadata, and zpool iostat telemetry.
        """
        if self.collect_zpool_iostat:
            return self._run_benchmark_with_zpool_iostat()
        else:
            return self._run_benchmark_without_zpool_iostat()
    
    def print_summary(self, results):
        """
        Print a formatted summary of the benchmark results.
        
        Args:
            results: The results dictionary from run()
        """
        escaped_pool_name = self.pool_name.replace(" ", "\\ ")
        print_header(f"DD Benchmark Results for Pool: {escaped_pool_name}")
        
        for result in results["benchmark_results"]:
            print_subheader(f"Threads: {result['threads']}")
            
            write_speeds = result['write_speeds']
            avg_write = result['average_write_speed']
            read_speeds = result['read_speeds']
            avg_read = result['average_read_speed']
            bytes_written = result['bytes_written']
            
            for i, speed in enumerate(write_speeds):
                print_bullet(f"1M Seq Write Run {i+1}: {color_text(f'{speed:.2f} MB/s', 'YELLOW')}")
            print_bullet(f"1M Seq Write Avg: {color_text(f'{avg_write:.2f} MB/s', 'GREEN')}")
            print_bullet(f"Total Written: {bytes_written/(1024**3):.2f} GiB")
            
            for i, speed in enumerate(read_speeds):
                print_bullet(f"1M Seq Read Run {i+1}: {color_text(f'{speed:.2f} MB/s', 'YELLOW')}")
            print_bullet(f"1M Seq Read Avg: {color_text(f'{avg_read:.2f} MB/s', 'GREEN')}")
        
        # Print zpool iostat summary if available
        if self.zpool_iostat_telemetry:
            self._print_zpool_iostat_summary()
    
    def _print_inline_telemetry_summary(self, escaped_pool_name: str):
        """Print telemetry summary immediately after benchmark (uses unified formatter)."""
        from core.zpool_iostat_collector import calculate_zpool_iostat_summary
        from core.telemetry_formatter import format_telemetry_for_console

        print_section(f"Zpool Iostat Telemetry Summary for Pool: {escaped_pool_name}")
        summary = calculate_zpool_iostat_summary(self.zpool_iostat_telemetry)
        output = format_telemetry_for_console(summary, escaped_pool_name)
        print(output)

    def _print_zpool_iostat_summary(self):
        """Print a comprehensive summary of the collected zpool iostat telemetry (delegates to inline)."""
        if not self.zpool_iostat_telemetry:
            return
        try:
            escaped_pool_name = self.pool_name.replace(" ", "\\ ")
            self._print_inline_telemetry_summary(escaped_pool_name)
        except ImportError as e:
            print_bullet(f"Import error: {e}")
            print_bullet(f"Total samples collected: {len(self.zpool_iostat_telemetry.samples)}")
        except Exception as e:
            print_error(f"Error generating summary: {e}")
            print_bullet(f"Total samples collected: {len(self.zpool_iostat_telemetry.samples)}")
    
    def get_zpool_iostat_data(self):
        """
        Get the collected zpool iostat telemetry data.
        
        Returns:
            ZpoolIostatTelemetry object or None if not collected
        """
        return self.zpool_iostat_telemetry
    
    def cleanup(self):
        """Remove any remaining test files (safety cleanup)."""
        print_info("Cleaning up any remaining test files...")
        thread_counts = [1, self.cores // 4, self.cores // 2, self.cores]
        max_threads = max(thread_counts)
        for i in range(max_threads):
            file_path = f"{self.dataset_path}/{self.file_prefix}{i}.dat"
            if os.path.exists(file_path):
                os.remove(file_path)
