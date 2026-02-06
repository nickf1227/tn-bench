"""
Individual disk benchmark - 4K sequential read tests.
"""

import subprocess
import time
from benchmarks.base import BenchmarkBase
from utils import (
    print_info, print_success, print_header, print_section,
    print_subheader, print_bullet, color_text
)


def run_dd_read_command(disk_name, read_size_gib):
    """
    Run a single 4K sequential read test on a disk.
    
    Args:
        disk_name: Name of the disk device (e.g., "nvme0n1")
        read_size_gib: Size to read in GiB
        
    Returns:
        float: Read speed in MB/s
    """
    print_info(f"Testing disk: {disk_name}")
    command = f"dd if=/dev/{disk_name} of=/dev/null bs=4K count={int(read_size_gib * 1024 * 1024 // 4)} status=none"
    start_time = time.time()
    subprocess.run(command, shell=True)
    end_time = time.time()
    total_time_taken = end_time - start_time
    total_bytes = read_size_gib * 1024 * 1024 * 1024
    read_speed = total_bytes / 1024 / 1024 / total_time_taken
    return read_speed


class DiskBenchmark(BenchmarkBase):
    """Individual disk 4K sequential read benchmark."""
    
    name = "disk"
    description = "Individual disk 4K sequential read benchmark"
    
    def __init__(self, disk_info, system_info, iterations=2):
        """
        Initialize disk benchmark.
        
        Args:
            disk_info: List of disk information dictionaries
            system_info: System information dictionary (for RAM size)
            iterations: Number of iterations to run per disk
        """
        self.disk_info = disk_info
        self.system_info = system_info
        self.iterations = iterations
    
    def validate(self) -> bool:
        """Check if we have disk information to test."""
        return len(self.disk_info) > 0
    
    @property
    def space_required_gib(self) -> int:
        """Disk benchmark doesn't require dataset space."""
        return 0
    
    def run(self, config: dict = None) -> list:
        """
        Run 4K sequential read benchmark on all disks.
        
        Returns:
            list: Results for each disk tested.
        """
        print_header("Disk Read Benchmark")
        print_info("This benchmark tests the 4K sequential read performance of each disk")
        print_info("To work around ARC caching, reads data = min(system RAM, disk size)")
        
        results = []
        system_ram_gib = self.system_info.get('physmem', 0) / (1024 ** 3)

        for disk in self.disk_info:
            disk_name = disk.get("name", "N/A")
            disk_size_gib = disk.get("size", 0) / (1024 ** 3)
            read_size_gib = min(system_ram_gib, disk_size_gib)

            if disk_name != "N/A":
                speeds = []
                print_section(f"Testing Disk: {disk_name}")
                for run_num in range(self.iterations):
                    speed = run_dd_read_command(disk_name, read_size_gib)
                    speeds.append(speed)
                    print_info(f"Run {run_num+1}: {color_text(f'{speed:.2f} MB/s', 'YELLOW')}")
                average_speed = sum(speeds) / len(speeds) if speeds else 0
                print_success(f"Average: {color_text(f'{average_speed:.2f} MB/s', 'GREEN')}")
                results.append({
                    "disk": disk_name,
                    "speeds": speeds,
                    "average_speed": average_speed,
                    "iterations": self.iterations
                })

        # Print summary
        print_header("Disk Read Benchmark Results")
        for result in results:
            print_subheader(f"Disk: {result['disk']}")
            
            speeds = result['speeds']
            avg_speed = result['average_speed']
            
            for i, speed in enumerate(speeds):
                print_bullet(f"Run {i+1}: {color_text(f'{speed:.2f} MB/s', 'YELLOW')}")
            print_bullet(f"Average: {color_text(f'{avg_speed:.2f} MB/s', 'GREEN')}")
        
        return results
