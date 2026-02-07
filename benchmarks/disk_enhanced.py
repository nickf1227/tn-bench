"""
Enhanced disk benchmark - multiple test modes and block sizes.
"""

import subprocess
import threading
import time
from benchmarks.base import BenchmarkBase
from utils import (
    print_info, print_success, print_error, print_header, print_section,
    print_subheader, print_bullet, color_text, print_warning
)

# Block size options
BLOCK_SIZES = {
    "1": {"size": "4K", "bytes": 4096, "description": "4K (small random I/O)"},
    "2": {"size": "32K", "bytes": 32768, "description": "32K (medium I/O)"},
    "3": {"size": "128K", "bytes": 131072, "description": "128K (large sequential)"},
    "4": {"size": "1M", "bytes": 1048576, "description": "1M (very large sequential)"}
}


def run_dd_read_command(disk_name, read_size_gib, block_size="1M"):
    """
    Run a disk read test with specified block size.
    
    Args:
        disk_name: Name of the disk device
        read_size_gib: Size to read in GiB
        block_size: Block size string (e.g., "4K", "1M")
        
    Returns:
        float: Read speed in MiB/s
    """
    block_bytes = BLOCK_SIZES.get(block_size, BLOCK_SIZES["4"])["bytes"]
    total_bytes = read_size_gib * 1024 * 1024 * 1024
    count = int(total_bytes / block_bytes)
    
    command = f"dd if=/dev/{disk_name} of=/dev/null bs={block_size} count={count} status=none"
    start_time = time.time()
    subprocess.run(command, shell=True)
    end_time = time.time()
    
    total_time_taken = end_time - start_time
    read_speed = total_bytes / 1024 / 1024 / total_time_taken
    return read_speed


class EnhancedDiskBenchmark(BenchmarkBase):
    """
    Enhanced individual disk benchmark with multiple test modes.
    
    Test modes:
    - serial: Test disks one at a time (baseline performance)
    - parallel: Test all disks simultaneously (controller stress test)
    - seek_stress: Multiple threads per disk (seek mechanism stress)
    """
    
    name = "enhanced_disk"
    description = "Enhanced individual disk benchmark with serial, parallel, and seek-stress modes"
    
    def __init__(self, disk_info, system_info, test_mode="serial", 
                 block_size="1M", iterations=2, seek_threads=4):
        """
        Initialize enhanced disk benchmark.
        
        Args:
            disk_info: List of disk information dictionaries
            system_info: System information dictionary
            test_mode: "serial", "parallel", or "seek_stress"
            block_size: Block size key ("1"=4K, "2"=32K, "3"=128K, "4"=1M)
            iterations: Number of iterations to run
            seek_threads: Number of threads per disk for seek_stress mode
        """
        self.disk_info = disk_info
        self.system_info = system_info
        self.test_mode = test_mode
        self.block_size = BLOCK_SIZES.get(block_size, BLOCK_SIZES["4"])["size"]
        self.block_desc = BLOCK_SIZES.get(block_size, BLOCK_SIZES["4"])["description"]
        self.iterations = iterations
        self.seek_threads = seek_threads
    
    def validate(self) -> bool:
        """Check if we have disk information to test."""
        return len(self.disk_info) > 0
    
    @property
    def space_required_gib(self) -> int:
        """Disk benchmark doesn't require dataset space."""
        return 0
    
    def run(self, config: dict = None) -> list:
        """
        Run the disk benchmark based on selected test mode.
        
        Returns:
            list: Results for each disk tested.
        """
        if self.test_mode == "serial":
            return self._run_serial()
        elif self.test_mode == "parallel":
            return self._run_parallel()
        elif self.test_mode == "seek_stress":
            return self._run_seek_stress()
        else:
            print_error(f"Unknown test mode: {self.test_mode}")
            return []
    
    def _calculate_read_size(self, disk):
        """Calculate read size for a disk (min of system RAM and disk size)."""
        system_ram_gib = self.system_info.get('physmem', 0) / (1024 ** 3)
        disk_size_gib = disk.get("size", 0) / (1024 ** 3)
        return min(system_ram_gib, disk_size_gib)
    
    def _run_serial(self):
        """Run serial benchmark - one disk at a time."""
        print_header("Serial Disk Benchmark")
        print_info("Testing disks one at a time for individual performance baseline")
        print_info(f"Block size: {self.block_desc}")
        
        results = []
        
        for disk in self.disk_info:
            disk_name = disk.get("name", "N/A")
            if disk_name == "N/A":
                continue
                
            read_size_gib = self._calculate_read_size(disk)
            speeds = []
            
            print_section(f"Testing Disk: {disk_name}")
            print_info(f"Read size: {read_size_gib:.2f} GiB")
            print_info(f"Model: {disk.get('model', 'N/A')}")
            
            for run_num in range(self.iterations):
                print_info(f"Run {run_num + 1} of {self.iterations}...")
                speed = run_dd_read_command(disk_name, read_size_gib, self.block_size)
                speeds.append(speed)
                print_info(f"Run {run_num+1}: {color_text(f'{speed:.2f} MiB/s', 'YELLOW')}")
            
            average_speed = sum(speeds) / len(speeds) if speeds else 0
            print_success(f"Average: {color_text(f'{average_speed:.2f} MiB/s', 'GREEN')}")
            
            results.append({
                "disk": disk_name,
                "model": disk.get("model", "N/A"),
                "serial": disk.get("serial", "N/A"),
                "size_gib": disk.get("size", 0) / (1024 ** 3),
                "block_size": self.block_size,
                "read_size_gib": read_size_gib,
                "speeds": speeds,
                "average_speed": average_speed,
                "iterations": self.iterations,
                "test_mode": "serial"
            })
        
        self._print_summary(results)
        return results
    
    def _run_parallel(self):
        """Run parallel benchmark - all disks simultaneously."""
        print_header("Parallel Disk Benchmark")
        print_info("Testing all disks simultaneously to stress disk controllers")
        print_info(f"Block size: {self.block_desc}")
        print_warning("This will heavily load your storage system!")
        
        results = []
        
        # Calculate read sizes for all disks
        disk_configs = []
        for disk in self.disk_info:
            disk_name = disk.get("name", "N/A")
            if disk_name != "N/A":
                read_size_gib = self._calculate_read_size(disk)
                disk_configs.append({
                    "name": disk_name,
                    "disk_info": disk,
                    "read_size_gib": read_size_gib
                })
        
        for run_num in range(self.iterations):
            print_section(f"Parallel Test Run {run_num + 1} of {self.iterations}")
            print_info(f"Testing {len(disk_configs)} disks simultaneously...")
            
            # Start all tests simultaneously
            threads = []
            run_results = {}
            
            def test_disk(disk_config, results_dict):
                speed = run_dd_read_command(
                    disk_config["name"], 
                    disk_config["read_size_gib"], 
                    self.block_size
                )
                results_dict[disk_config["name"]] = speed
            
            start_time = time.time()
            for disk_config in disk_configs:
                thread = threading.Thread(
                    target=test_disk, 
                    args=(disk_config, run_results)
                )
                thread.start()
                threads.append(thread)
            
            # Wait for all to complete
            for thread in threads:
                thread.join()
            end_time = time.time()
            
            parallel_duration = end_time - start_time
            print_info(f"Parallel run completed in {parallel_duration:.1f} seconds")
            
            # Store results
            for disk_config in disk_configs:
                disk_name = disk_config["name"]
                speed = run_results.get(disk_name, 0)
                
                # Find or create result entry
                existing = next((r for r in results if r["disk"] == disk_name), None)
                if existing:
                    existing["speeds"].append(speed)
                else:
                    results.append({
                        "disk": disk_name,
                        "model": disk_config["disk_info"].get("model", "N/A"),
                        "serial": disk_config["disk_info"].get("serial", "N/A"),
                        "size_gib": disk_config["disk_info"].get("size", 0) / (1024 ** 3),
                        "block_size": self.block_size,
                        "read_size_gib": disk_config["read_size_gib"],
                        "speeds": [speed],
                        "test_mode": "parallel"
                    })
        
        # Calculate averages
        for result in results:
            result["average_speed"] = sum(result["speeds"]) / len(result["speeds"])
            result["iterations"] = self.iterations
        
        self._print_summary(results)
        return results
    
    def _run_seek_stress(self):
        """Run seek-stress benchmark - multiple threads per disk."""
        print_header("Seek-Stress Disk Benchmark")
        print_info(f"Testing disks with {self.seek_threads} concurrent threads per disk")
        print_info(f"Block size: {self.block_desc}")
        print_warning("This will heavily stress individual disk seek mechanisms!")
        
        results = []
        
        # Fixed read size for seek test (50 GiB per thread)
        base_read_size_gib = 50
        
        for run_num in range(self.iterations):
            print_section(f"Seek-Stress Run {run_num + 1} of {self.iterations}")
            
            all_threads = []
            run_results = {}
            
            def test_disk_thread(disk_name, read_size, thread_id, results_dict):
                speed = run_dd_read_command(disk_name, read_size, self.block_size)
                key = f"{disk_name}_thread_{thread_id}"
                results_dict[key] = {
                    "speed": speed,
                    "disk_name": disk_name,
                    "thread_id": thread_id
                }
                print_info(f"  {disk_name} thread {thread_id}: {speed:.0f} MiB/s")
            
            # Start threads for all disks
            start_time = time.time()
            for disk in self.disk_info:
                disk_name = disk.get("name", "N/A")
                if disk_name == "N/A":
                    continue
                
                disk_size_gib = disk.get("size", 0) / (1024 ** 3)
                read_size_gib = min(base_read_size_gib, disk_size_gib)
                
                for thread_id in range(self.seek_threads):
                    thread = threading.Thread(
                        target=test_disk_thread,
                        args=(disk_name, read_size_gib, thread_id, run_results)
                    )
                    thread.start()
                    all_threads.append(thread)
            
            # Wait for all threads
            print_info(f"Waiting for {len(all_threads)} threads to complete...")
            for thread in all_threads:
                thread.join()
            end_time = time.time()
            
            duration = end_time - start_time
            print_info(f"Seek-stress run completed in {duration:.1f} seconds")
            
            # Aggregate results by disk
            disk_threads = {}
            for key, data in run_results.items():
                disk_name = data["disk_name"]
                if disk_name not in disk_threads:
                    disk_threads[disk_name] = []
                disk_threads[disk_name].append(data["speed"])
            
            # Store aggregated results
            for disk in self.disk_info:
                disk_name = disk.get("name", "N/A")
                if disk_name not in disk_threads:
                    continue
                
                thread_speeds = disk_threads[disk_name]
                avg_speed = sum(thread_speeds) / len(thread_speeds)
                
                existing = next((r for r in results if r["disk"] == disk_name), None)
                if existing:
                    existing["speeds"].append(avg_speed)
                else:
                    results.append({
                        "disk": disk_name,
                        "model": disk.get("model", "N/A"),
                        "serial": disk.get("serial", "N/A"),
                        "size_gib": disk.get("size", 0) / (1024 ** 3),
                        "block_size": self.block_size,
                        "read_size_gib": base_read_size_gib,
                        "thread_count": self.seek_threads,
                        "speeds": [avg_speed],
                        "test_mode": "seek_stress"
                    })
        
        # Calculate averages
        for result in results:
            result["average_speed"] = sum(result["speeds"]) / len(result["speeds"])
            result["iterations"] = self.iterations
        
        self._print_summary(results)
        return results
    
    def _print_summary(self, results):
        """Print summary of benchmark results."""
        if not results:
            return
        
        print_header(f"Disk Benchmark Results - {self.test_mode.upper()} Mode")
        
        # Group by test mode (in case we have mixed results)
        mode_results = {}
        for result in results:
            mode = result.get("test_mode", "unknown")
            if mode not in mode_results:
                mode_results[mode] = []
            mode_results[mode].append(result)
        
        for mode, mode_data in mode_results.items():
            print_subheader(f"Mode: {mode.upper()}")
            
            for result in mode_data:
                print_bullet(f"Disk: {result['disk']}")
                print_bullet(f"Model: {result.get('model', 'N/A')}")
                
                speeds = result['speeds']
                avg_speed = result['average_speed']
                
                for i, speed in enumerate(speeds):
                    print_bullet(f"  Run {i+1}: {color_text(f'{speed:.2f} MiB/s', 'YELLOW')}")
                
                print_bullet(f"  Average: {color_text(f'{avg_speed:.2f} MiB/s', 'GREEN')}")
                
                if result.get("thread_count"):
                    print_bullet(f"  Threads: {result['thread_count']}")
                print()
        
        # Print simple statistics
        if len(results) > 1:
            all_speeds = [r["average_speed"] for r in results]
            overall_avg = sum(all_speeds) / len(all_speeds)
            print_subheader("Overall Statistics")
            print_info(f"Disks tested: {len(results)}")
            print_info(f"Average speed: {overall_avg:.2f} MiB/s")
            print_info(f"Speed range: {min(all_speeds):.2f} - {max(all_speeds):.2f} MiB/s")
