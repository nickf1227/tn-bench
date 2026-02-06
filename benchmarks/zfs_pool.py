"""
ZFS Pool benchmark - sequential write/read across varying thread counts.
Space-optimized version: cleans up test files between iterations to reduce space requirements.
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


def run_single_iteration(threads, bytes_per_thread, block_size, file_prefix, dataset_path, iteration_num):
    """
    Run a single write/read iteration and cleanup.
    
    Returns:
        tuple: (write_speed, read_speed, bytes_written)
    """
    # Write phase
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
    """ZFS Pool sequential write/read benchmark."""
    
    name = "zfs_pool"
    description = "ZFS Pool sequential write/read benchmark with varying thread counts"
    
    def __init__(self, pool_name, cores, dataset_path, iterations=2):
        self.pool_name = pool_name
        self.cores = cores
        self.dataset_path = dataset_path
        self.iterations = iterations
        self.bytes_per_thread = 20480  # 20 GiB per thread
        self.block_size = "1M"
        self.file_prefix = "file_"
    
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
    
    def run(self, config: dict = None) -> dict:
        """
        Run the ZFS pool benchmark across four thread-count configurations.
        Cleans up test files between iterations to minimize space usage.
        
        Returns:
            dict: Results containing thread counts, speeds, and metadata.
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

        # Print summary
        print_header(f"DD Benchmark Results for Pool: {escaped_pool_name}")
        for result in results:
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
        
        return {
            "benchmark_results": results,
            "total_bytes_written": total_bytes_written
        }
    
    def cleanup(self):
        """Remove any remaining test files (safety cleanup)."""
        print_info("Cleaning up any remaining test files...")
        thread_counts = [1, self.cores // 4, self.cores // 2, self.cores]
        max_threads = max(thread_counts)
        for i in range(max_threads):
            file_path = f"{self.dataset_path}/{self.file_prefix}{i}.dat"
            if os.path.exists(file_path):
                os.remove(file_path)
