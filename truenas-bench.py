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
import json
import os
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
from core.analytics import ResultAnalyzer
from core.report_generator import generate_markdown_report
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


def ask_disk_test_modes():
    """Ask user for disk test mode(s) - supports multi-select."""
    print_header("Disk Test Mode Selection")
    print_info("Select the disk benchmark test mode(s):")
    print()
    print_bullet("1. SERIAL - Test disks one at a time (baseline performance)")
    print_bullet("2. PARALLEL - Test all disks simultaneously (controller stress)")
    print_bullet("3. SEEK_STRESS - Multiple threads per disk (seek mechanism stress)")
    print()
    print_info("You can select multiple modes by entering comma-separated numbers.")
    print_info("Examples: '1' (serial only), '1,2' (serial then parallel), 'all' (all modes)")
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
    
    mode_map = {
        "1": "serial",
        "2": "parallel", 
        "3": "seek_stress"
    }
    
    while True:
        response = input(color_text("\nEnter test mode(s) (1/2/3, comma-separated, or 'all') [1]: ", "BOLD")).strip().lower()
        
        if not response or response == "1":
            return ["serial"]
        elif response == "all":
            print_warning("⚠️  All modes selected - this will take a very long time!")
            return ["serial", "parallel", "seek_stress"]
        
        # Parse comma-separated selections
        selections = [s.strip() for s in response.split(",")]
        modes = []
        valid = True
        
        for selection in selections:
            if selection in mode_map:
                modes.append(mode_map[selection])
            else:
                print_error(f"Invalid selection: {selection}")
                valid = False
                break
        
        if valid and modes:
            # Show warnings for intensive modes
            if "parallel" in modes:
                print_warning("⚠️  PARALLEL mode included - expect heavy controller load!")
            if "seek_stress" in modes:
                print_error("⚠️  SEEK_STRESS mode included - high CPU usage expected!")
                print_warning("Ensure system is not running other workloads.")
            
            return modes
        elif not valid:
            print_error("Invalid choice. Please enter 1, 2, 3, comma-separated values, or 'all'")


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
    
    disk_test_modes = ["serial"]
    block_size = "4"
    seek_threads = 4
    
    if run_disk_bench:
        disk_test_modes = ask_disk_test_modes()
        block_size = ask_disk_block_size()
        if "seek_stress" in disk_test_modes:
            seek_threads = ask_seek_threads()
        
        benchmark_results["benchmark_config"]["disk_test_modes"] = disk_test_modes
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
            print_info(f"Space required:  {required_gib:.2f} GiB (20 GiB/thread × {cores} threads)")
            print_info(f"Test iterations: {zfs_iterations} (space freed between iterations)")
            
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
        all_disk_results = []
        
        # Run each selected test mode
        for mode in disk_test_modes:
            print_header("Disk Benchmark Configuration")
            print_info(f"Test mode: {mode}")
            print_info(f"Block size: {BLOCK_SIZES[block_size]['description']}")
            if mode == "seek_stress":
                print_info(f"Threads per disk: {seek_threads}")
            
            disk_benchmark = EnhancedDiskBenchmark(
                disk_info, system_info, 
                test_mode=mode,
                block_size=block_size,
                iterations=disk_iterations,
                seek_threads=seek_threads
            )
            mode_results = disk_benchmark.run()
            all_disk_results.extend(mode_results)
        
        benchmark_results["disk_benchmark"] = all_disk_results

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
    
    # Run analytics and generate reports
    print_header("Analytics")
    print_info("Running post-benchmark analytics...")
    
    try:
        # Load the saved results for analysis
        with open(args.output, 'r') as f:
            results_for_analysis = json.load(f)
        
        # Run analytics
        analyzer = ResultAnalyzer(results_for_analysis)
        analysis = analyzer.analyze()
        
        # Generate analytics JSON filename
        base_path = args.output.replace('.json', '')
        analytics_path = f"{base_path}_analytics.json"
        report_path = f"{base_path}_report.md"
        
        # Save analytics JSON
        with open(analytics_path, 'w') as f:
            json.dump(analysis.to_dict(), f, indent=2)
        print_success(f"Analytics data saved to: {os.path.abspath(analytics_path)}")
        
        # Generate and save markdown report
        report = generate_markdown_report(analysis.to_dict(), args.output)
        with open(report_path, 'w') as f:
            f.write(report)
        print_success(f"Analytics report saved to: {os.path.abspath(report_path)}")
        
        # Print summary
        print_section("Analytics Summary")
        for pool in analysis.pool_analyses:
            print_info(f"Pool: {pool.name}")
            if pool.write_scaling:
                print_bullet(f"Write peak: {pool.write_scaling.get('peak_speed_mbps', 0)} MB/s @ {pool.write_scaling.get('optimal_threads', 0)} threads")
            if pool.read_scaling:
                print_bullet(f"Read peak: {pool.read_scaling.get('peak_speed_mbps', 0)} MB/s @ {pool.read_scaling.get('optimal_threads', 0)} threads")
        
    except Exception as e:
        print_error(f"Analytics generation failed (non-critical): {str(e)}")


if __name__ == "__main__":
    from utils import print_warning, print_error, print_section, print_bullet
    main()
