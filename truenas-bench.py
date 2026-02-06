#!/usr/bin/env python3
"""
TN-Bench v2.0 - TrueNAS System Benchmark

Modular architecture with core functionality split into:
- utils: Common utilities and formatting
- core: System info, dataset management, results handling
- benchmarks: Individual benchmark implementations

This script serves as the user interface and coordination layer.
"""

import argparse
import time

from utils import (
    print_header, print_info, print_success, color_text
)
from core import (
    get_system_info, print_system_info_table,
    get_pool_info, print_pool_info_table,
    get_disk_info, get_pool_membership, print_disk_info_table
)
from core.dataset import create_dataset, delete_dataset, validate_space
from core.results import save_results_to_json
from benchmarks import ZFSPoolBenchmark, DiskBenchmark, EnhancedDiskBenchmark, BLOCK_SIZES


def get_user_confirmation():
    """Display welcome message and get user confirmation to proceed."""
    print_header("TN-Bench v2.0 (Modular)")
    print(color_text("TN-Bench is an OpenSource Software Script that uses standard tools to", "BOLD"))
    print(color_text("Benchmark your System and collect various statistical information via", "BOLD"))
    print(color_text("the TrueNAS API.", "BOLD"))
    print()
    
    print_info("TN-Bench will create a Dataset in each of your pools for testing purposes")
    print_info("that will consume 20 GiB of space for every thread in your system.")
    print()
    
    print_warning("This test will make your system EXTREMELY slow during its run.")
    print_warning("It is recommended to run this test when no other workloads are running.")
    print()
    
    print_info("ZFS ARC will impact your results. You can set zfs_arc_max to 1 to prevent ARC caching.")
    print_info("Setting it back to 0 restores default behavior but requires a system restart.")
    
    print_section("Confirmation")
    continue_benchmark = input(color_text("Would you like to continue? (yes/no): ", "BOLD"))
    if continue_benchmark.lower() != 'yes':
        print_info("Exiting TN-Bench.")
        exit(0)


def select_pools_to_test(pool_info):
    """Interactive pool selection."""
    print_header("Pool Selection")
    print_info("Available pools:")
    for i, pool in enumerate(pool_info):
        print_bullet(f"{i+1}. {pool['name']}")
    
    print_info("Options:")
    print_bullet("1. Enter specific pool numbers (comma separated)")
    print_bullet("2. Type 'all' to test all pools")
    print_bullet("3. Type 'none' to skip pool testing")
    
    while True:
        selection = input(color_text("\nEnter your choice [all]: ", "BOLD")).strip()
        if not selection:
            return pool_info
        
        if selection.lower() == 'all':
            return pool_info
        
        if selection.lower() == 'none':
            return []
        
        try:
            selected_indices = [int(idx.strip()) - 1 for idx in selection.split(',')]
            selected_pools = []
            for idx in selected_indices:
                if 0 <= idx < len(pool_info):
                    selected_pools.append(pool_info[idx])
                else:
                    print_warning(f"Index {idx+1} is out of range. Skipping.")
            return selected_pools
        except ValueError:
            print_error("Invalid input. Please enter pool numbers (e.g., '1,3'), 'all', or 'none'.")


def ask_iteration_count(benchmark_type, default=2):
    """Ask user for iteration count for a benchmark type."""
    print_header(f"{benchmark_type} Benchmark Iterations")
    print_info("How many times should we run each test?")
    print_bullet(f"• Enter any positive integer (1-100, default: {default})")
    print_bullet(f"• Enter 0 to skip this benchmark")
    
    while True:
        response = input(color_text(f"\nEnter iteration count [{default}]: ", "BOLD")).strip()
        if not response:
            return default
        
        try:
            count = int(response)
            if count == 0:
                print_info(f"Skipping {benchmark_type} benchmark.")
                return 0
            if 1 <= count <= 100:
                return count
            print_error("Please enter a number between 0 and 100")
        except ValueError:
            print_error("Invalid input. Please enter a number")


def ask_disk_test_mode():
    """Ask user for disk test mode."""
    print_header("Disk Test Mode Selection")
    print_info("Select the disk benchmark test mode:")
    print()
    print_bullet("1. SERIAL - Test disks one at a time (baseline performance)")
    print_bullet("2. PARALLEL - Test all disks simultaneously (controller stress)")
    print_bullet("3. SEEK_STRESS - Multiple threads per disk (seek mechanism stress)")
    print()
    print_info("SERIAL is recommended for baseline measurements.")
    print_info("PARALLEL tests controller/chassis backplane throughput.")
    print_info("SEEK_STRESS tests disk seek performance under heavy load.")
    print()
    print_warning("⚠️  RESOURCE WARNING:")
    print_warning("PARALLEL mode will heavily load your storage controllers.")
    print_warning("SEEK_STRESS uses multiple threads per disk and may cause:")
    print_warning("  - High CPU usage (can saturate all cores)")
    print_warning("  - System instability on heavily loaded systems")
    print_warning("  - Significantly longer test durations")
    print_info("For production systems, use SERIAL mode only.")
    
    while True:
        response = input(color_text("\nEnter test mode (1/2/3) [1]: ", "BOLD")).strip()
        if not response or response == "1":
            return "serial"
        elif response == "2":
            print_warning("⚠️  PARALLEL mode selected - expect heavy controller load!")
            return "parallel"
        elif response == "3":
            print_error("⚠️  SEEK_STRESS mode selected - high CPU usage expected!")
            print_warning("Ensure system is not running other workloads.")
            return "seek_stress"
        else:
            print_error("Invalid choice. Please enter 1, 2, or 3")


def ask_disk_block_size():
    """Ask user for disk benchmark block size."""
    print_header("Disk Block Size Selection")
    print_info("Select the block size for disk testing:")
    print()
    
    for key, info in BLOCK_SIZES.items():
        print_bullet(f"{key}. {info['description']}")
    print()
    print_info("4K tests small random I/O performance.")
    print_info("1M tests large sequential throughput.")
    
    while True:
        response = input(color_text("\nEnter block size (1/2/3/4) [4]: ", "BOLD")).strip()
        if not response or response == "4":
            return "4"
        elif response in BLOCK_SIZES:
            return response
        else:
            print_error("Invalid choice. Please enter 1, 2, 3, or 4")


def ask_disk_test_mode():
    """Ask user for disk benchmark test mode."""
    print_header("Disk Benchmark Test Mode")
    print_info("Select the test mode for individual disk benchmarks:")
    print_bullet("1. serial    - Test disks one at a time (baseline performance)")
    print_bullet("2. parallel  - Test all disks simultaneously (controller stress)")
    print_bullet("3. seek_stress - Multiple threads per disk (seek mechanism stress)")
    
    while True:
        response = input(color_text("\nSelect test mode [1]: ", "BOLD")).strip()
        if not response or response == "1":
            return "serial"
        elif response == "2":
            return "parallel"
        elif response == "3":
            return "seek_stress"
        else:
            print_error("Invalid selection. Please enter 1, 2, or 3")


def ask_block_size():
    """Ask user for block size."""
    print_header("Disk Benchmark Block Size")
    print_info("Select the block size for disk benchmarks:")
    for key, info in BLOCK_SIZES.items():
        print_bullet(f"{key}. {info['description']}")
    
    while True:
        response = input(color_text("\nSelect block size [4]: ", "BOLD")).strip()
        if not response:
            return "4"  # Default to 1M
        if response in BLOCK_SIZES:
            return response
        print_error("Invalid selection. Please enter 1, 2, 3, or 4")


def ask_seek_threads():
    """Ask user for number of threads in seek_stress mode."""
    print_header("Seek-Stress Thread Count")
    print_info("How many concurrent threads per disk for seek-stress mode?")
    print_bullet("• More threads = higher stress on disk seek mechanisms")
    print_bullet("• Recommended: 4-8 threads per disk")
    
    while True:
        response = input(color_text("\nEnter thread count [4]: ", "BOLD")).strip()
        if not response:
            return 4
        try:
            count = int(response)
            if 1 <= count <= 32:
                return count
            print_error("Please enter a number between 1 and 32")
        except ValueError:
            print_error("Invalid input. Please enter a number")


def calculate_dwpd(total_writes_gib, pool_capacity_gib, test_duration_seconds):
    """Calculate Drive Writes Per Day (DWPD)."""
    if pool_capacity_gib <= 0:
        return 0.0
    
    writes_per_second = total_writes_gib / pool_capacity_gib / test_duration_seconds
    dwpd = writes_per_second * 86400  # 86400 seconds in a day
    return dwpd


def main():
    parser = argparse.ArgumentParser(description='TN-Bench System Benchmark')
    parser.add_argument('--output', type=str, default='./tn_bench_results.json',
                        help='Path to output JSON file (default: ./tn_bench_results.json)')
    args = parser.parse_args()

    benchmark_results = {
        "system_info": {},
        "pools": [],
        "disk_benchmark": [],
        "total_benchmark_time_minutes": 0,
        "benchmark_config": {
            "selected_pools": [],
            "disk_benchmark_run": False,
            "zfs_iterations": 2,
            "disk_iterations": 2
        }
    }

    get_user_confirmation()
    start_time = time.time()

    # Collect system information
    system_info = get_system_info()
    benchmark_results["system_info"] = system_info
    print_system_info_table(system_info)
    
    # Collect pool information
    pool_info = get_pool_info()
    benchmark_results["pools"] = pool_info
    print_pool_info_table(pool_info)

    # Collect disk information
    disk_info = get_disk_info()
    pool_membership = get_pool_membership()
    benchmark_results["disks"] = disk_info
    benchmark_results["pool_membership"] = pool_membership
    print_disk_info_table(disk_info, pool_membership)

    # Ask user which pools to test
    selected_pools = select_pools_to_test(pool_info)
    benchmark_results["benchmark_config"]["selected_pools"] = [p['name'] for p in selected_pools]
    
    # Ask about ZFS iterations
    zfs_iterations = ask_iteration_count("ZFS Pool")
    benchmark_results["benchmark_config"]["zfs_iterations"] = zfs_iterations
    
    # Ask about disk benchmark iterations and options
    disk_iterations = ask_iteration_count("Individual Disk")
    run_disk_bench = disk_iterations > 0
    benchmark_results["benchmark_config"]["disk_benchmark_run"] = run_disk_bench
    benchmark_results["benchmark_config"]["disk_iterations"] = disk_iterations
    
    disk_test_mode = "serial"
    block_size = "4"
    seek_threads = 4
    
    if run_disk_bench:
        disk_test_mode = ask_disk_test_mode()
        block_size = ask_block_size()
        if disk_test_mode == "seek_stress":
            seek_threads = ask_seek_threads()
        
        benchmark_results["benchmark_config"]["disk_test_mode"] = disk_test_mode
        benchmark_results["benchmark_config"]["disk_block_size"] = BLOCK_SIZES[block_size]["size"]
        benchmark_results["benchmark_config"]["disk_seek_threads"] = seek_threads

    cores = system_info.get("cores", 1)

    print_header("DD Benchmark Starting")
    print_info(f"Using {cores} threads for the benchmark.")
    
    if zfs_iterations > 0:
        print_info(f"ZFS tests will run {zfs_iterations} time(s) per configuration")
    else:
        print_info("Skipping ZFS pool benchmark")
    
    if disk_iterations > 0:
        print_info(f"Disk tests will run {disk_iterations} time(s) per disk")
    else:
        print_info("Skipping individual disk benchmark")

    # Run benchmarks for each selected pool
    for pool in selected_pools:
        if zfs_iterations == 0:
            break
            
        pool_name = pool.get('name', 'N/A')
        pool_start_time = time.time()
        print_header(f"Testing Pool: {pool_name}")
        print_info(f"Creating test dataset for pool: {pool_name}")
        dataset_path = create_dataset(pool_name)
        
        if dataset_path:
            # Check available space
            has_space, available_gib, required_gib = validate_space(pool_name, cores, zfs_iterations)
            
            print_section("Space Verification")
            print_info(f"Available space: {available_gib:.2f} GiB")
            print_info(f"Space required:  {required_gib:.2f} GiB (20 GiB/thread × {cores} threads × {zfs_iterations} iterations)")
            
            if not has_space:
                print_warning(f"Insufficient space in dataset {pool_name}/tn-bench")
                print_warning(f"Minimum required: {required_gib} GiB")
                print_warning(f"Available:        {available_gib:.2f} GiB")
                proceed = input(color_text("\nProceed anyway? (yes/no): ", "BOLD")).lower()
                if proceed != 'yes':
                    print_info(f"Skipping benchmarks for pool {pool_name}")
                    delete_dataset(f"{pool_name}/tn-bench")
                    continue

            print_success("Sufficient space available - proceeding with benchmarks")
            
            # Run ZFS pool benchmark using the modular benchmark class
            zfs_benchmark = ZFSPoolBenchmark(pool_name, cores, dataset_path, zfs_iterations)
            pool_bench_results = zfs_benchmark.run()
            total_bytes_written = pool_bench_results["total_bytes_written"]
            
            pool_end_time = time.time()
            pool_duration = pool_end_time - pool_start_time
            
            # Get pool capacity for DWPD calculation
            pool_capacity_bytes = None
            for p in pool_info:
                if p['name'] == pool_name:
                    pool_capacity_bytes = p.get('size', 0)
                    break
            
            total_writes_gib = total_bytes_written / (1024 ** 3)
            pool_capacity_gib = pool_capacity_bytes / (1024 ** 3) if pool_capacity_bytes else 0
            
            # Calculate DWPD
            dwpd = calculate_dwpd(total_writes_gib, pool_capacity_gib, pool_duration)
            
            # Print summary
            print_section("Pool Write Summary")
            print_info(f"Total data written: {total_writes_gib:.2f} GiB")
            print_info(f"Pool capacity: {pool_capacity_gib:.2f} GiB")
            print_info(f"Benchmark duration: {pool_duration:.2f} seconds")
            print_info(f"Drive Writes Per Day (DWPD): {dwpd:.2f}")
            
            # Store pool benchmark results
            for pool_entry in benchmark_results["pools"]:
                if pool_entry["name"] == pool_name:
                    pool_entry["benchmark_results"] = pool_bench_results["benchmark_results"]
                    pool_entry["total_writes_gib"] = total_writes_gib
                    pool_entry["dwpd"] = dwpd
                    pool_entry["benchmark_duration_seconds"] = pool_duration
                    break
            
            zfs_benchmark.cleanup()

    # Run disk benchmark if requested
    if run_disk_bench:
        print_header("Disk Benchmark Configuration")
        print_info(f"Test mode: {disk_test_mode}")
        print_info(f"Block size: {BLOCK_SIZES[block_size]['description']}")
        if disk_test_mode == "seek_stress":
            print_info(f"Threads per disk: {seek_threads}")
        
        disk_benchmark = EnhancedDiskBenchmark(
            disk_info, system_info, 
            test_mode=disk_test_mode,
            block_size=block_size,
            iterations=disk_iterations,
            seek_threads=seek_threads
        )
        disk_bench_results = disk_benchmark.run()
        benchmark_results["disk_benchmark"] = disk_bench_results

    end_time = time.time()
    total_time_taken = end_time - start_time
    total_time_taken_minutes = total_time_taken / 60
    benchmark_results["total_benchmark_time_minutes"] = total_time_taken_minutes
    
    print_header("Benchmark Complete")
    print_success(f"Total benchmark time: {total_time_taken_minutes:.2f} minutes")

    # Cleanup datasets
    for pool in selected_pools:
        if zfs_iterations == 0:
            break
            
        pool_name = pool.get('name', 'N/A')
        dataset_name = f"{pool_name}/tn-bench"
        delete = input(color_text(f"\nDelete testing dataset {dataset_name}? (yes/no): ", "BOLD")).lower()
        if delete == 'yes':
            delete_dataset(dataset_name)
            print_success(f"Dataset {dataset_name} deleted.")
        else:
            print_info(f"Dataset {dataset_name} not deleted.")

    # Save results to JSON
    save_results_to_json(benchmark_results, args.output, start_time, end_time)


if __name__ == "__main__":
    from utils import print_warning, print_error, print_section, print_bullet
    main()
