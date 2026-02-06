"""
ZFS Pool benchmark - sequential write/read across varying thread counts.
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


def run_write_benchmark(threads, bytes_per_thread, block_size, file_prefix, dataset_path, iterations=2):
    """
    Run write benchmark with specified thread count.
    
    Returns:
        tuple: (speeds list, average speed, total bytes written)
    """
    print_info(f"Running DD write benchmark with {threads} threads...")
    speeds = []
    total_bytes_written = 0

    for run in range(iterations):
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
        
        # Calculate bytes written in this run
        block_size_bytes = 1024*1024  # 1M = 1,048,576 bytes
        bytes_this_run = threads * bytes_per_thread * block_size_bytes
        total_bytes_written += bytes_this_run
        
        write_speed = bytes_this_run / total_time_taken / (1024*1024)  # MB/s
        speeds.append(write_speed)
        print_info(f"Run {run + 1} write speed: {color_text(f'{write_speed:.2f} MB/s', 'YELLOW')}")
        print_info(f"Run {run + 1} wrote: {bytes_this_run/(1024**3):.2f} GiB")

    average_write_speed = sum(speeds) / len(speeds) if speeds else 0
    print_success(f"Average write speed: {color_text(f'{average_write_speed:.2f} MB/s', 'GREEN')}")
    return speeds, average_write_speed, total_bytes_written


def run_read_benchmark(threads, bytes_per_thread, block_size, file_prefix, dataset_path, iterations=2):
    """
    Run read benchmark with specified thread count.
    
    Returns:
        tuple: (speeds list, average speed)
    """
    print_info(f"Running DD read benchmark with {threads} threads...")
    speeds = []

    for run in range(iterations):
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
        total_bytes = threads * bytes_per_thread * 1024 * 1024
        read_speed = total_bytes / 1024 / 1024 / total_time_taken
        speeds.append(read_speed)
        print_info(f"Run {run + 1} read speed: {color_text(f'{read_speed:.2f} MB/s', 'YELLOW')}")

    average_read_speed = sum(speeds) / len(speeds) if speeds else 0
    print_success(f"Average read speed: {color_text(f'{average_read_speed:.2f} MB/s', 'GREEN')}")
    return speeds, average_read_speed


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
        """Calculate space required: 20 GiB per thread across 4 configurations."""
        max_threads = self.cores
        return 20 * max_threads * self.iterations
    
    def run(self, config: dict = None) -> dict:
        """
        Run the ZFS pool benchmark across four thread-count configurations.
        
        Returns:
            dict: Results containing thread counts, speeds, and metadata.
        """
        escaped_pool_name = self.pool_name.replace(" ", "\\ ")
        thread_counts = [1, self.cores // 4, self.cores // 2, self.cores]
        results = []
        total_bytes_written = 0

        for threads in thread_counts:
            print_section(f"Testing Pool: {escaped_pool_name} - Threads: {threads}")
            write_speeds, average_write_speed, bytes_written = run_write_benchmark(
                threads, self.bytes_per_thread, self.block_size, 
                self.file_prefix, self.dataset_path, self.iterations
            )
            total_bytes_written += bytes_written
            
            read_speeds, average_read_speed = run_read_benchmark(
                threads, self.bytes_per_thread, self.block_size,
                self.file_prefix, self.dataset_path, self.iterations
            )
            results.append({
                "threads": threads,
                "write_speeds": write_speeds,
                "average_write_speed": average_write_speed,
                "read_speeds": read_speeds,
                "average_read_speed": average_read_speed,
                "iterations": self.iterations,
                "bytes_written": bytes_written
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
        """Remove test files from dataset."""
        print_info("Cleaning up test files...")
        escaped_dataset_path = self.dataset_path.replace(" ", "\\ ")
        for file in os.listdir(escaped_dataset_path):
            if file.startswith(self.file_prefix) and file.endswith('.dat'):
                os.remove(os.path.join(escaped_dataset_path, file))
