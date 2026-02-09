"""
Results management and JSON output for tn-bench.
"""

import json
import os
import time
from utils import print_success, print_error, print_info


def save_results_to_json(results, output_path, start_time, end_time):
    """
    Transform and save benchmark results to JSON.
    
    Args:
        results: Raw benchmark results dictionary
        output_path: Path to write JSON file
        start_time: Benchmark start timestamp
        end_time: Benchmark end timestamp
    """
    try:
        # Transform results to match README schema
        transformed_results = {
            "schema_version": "1.0",
            "metadata": {
                "start_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start_time)),
                "end_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(end_time)),
                "duration_minutes": round((end_time - start_time) / 60, 2),
                "benchmark_config": results.get("benchmark_config", {})
            },
            "system": {
                "os_version": results.get("system_info", {}).get("version", "N/A"),
                "load_average_1m": results.get("system_info", {}).get("loadavg", ["N/A", "N/A", "N/A"])[0],
                "load_average_5m": results.get("system_info", {}).get("loadavg", ["N/A", "N/A", "N/A"])[1],
                "load_average_15m": results.get("system_info", {}).get("loadavg", ["N/A", "N/A", "N/A"])[2],
                "cpu_model": results.get("system_info", {}).get("model", "N/A"),
                "logical_cores": results.get("system_info", {}).get("cores", "N/A"),
                "physical_cores": results.get("system_info", {}).get("physical_cores", "N/A"),
                "system_product": results.get("system_info", {}).get("system_product", "N/A"),
                "memory_gib": round(results.get("system_info", {}).get("physmem", 0) / (1024 ** 3), 2)
            },
            "pools": [],
            "disks": []
        }
        
        # Process pools
        for pool in results.get("pools", []):
            pool_entry = {
                "name": pool.get("name", "N/A"),
                "path": pool.get("path", "N/A"),
                "status": pool.get("status", "N/A"),
                "vdevs": [],
                "benchmark": []
            }
            
            # Extract vdev information
            topology = pool.get("topology", {})
            data = topology.get("data", []) if topology else []
            for vdev in data:
                vdev_entry = {
                    "name": vdev.get("name", "N/A"),
                    "type": vdev.get("type", "N/A"),
                    "disk_count": len(vdev.get("children", []))
                }
                pool_entry["vdevs"].append(vdev_entry)
            
            # Add benchmark results if available
            if "benchmark_results" in pool:
                for bench in pool["benchmark_results"]:
                    bench_entry = {
                        "threads": bench["threads"],
                        "write_speeds": [round(s, 2) for s in bench["write_speeds"]],
                        "average_write_speed": round(bench["average_write_speed"], 2),
                        "read_speeds": [round(s, 2) for s in bench["read_speeds"]],
                        "average_read_speed": round(bench["average_read_speed"], 2),
                        "iterations": bench["iterations"]
                    }
                    pool_entry["benchmark"].append(bench_entry)
            
            # Add zpool iostat telemetry if available
            if "zpool_iostat_telemetry" in pool and pool["zpool_iostat_telemetry"]:
                iostat = pool["zpool_iostat_telemetry"]
                pool_entry["zpool_iostat_telemetry"] = {
                    "pool_name": iostat.get("pool_name"),
                    "start_time": iostat.get("start_time"),
                    "start_time_iso": iostat.get("start_time_iso"),
                    "end_time": iostat.get("end_time"),
                    "end_time_iso": iostat.get("end_time_iso"),
                    "duration_seconds": iostat.get("duration_seconds"),
                    "warmup_iterations": iostat.get("warmup_iterations"),
                    "cooldown_iterations": iostat.get("cooldown_iterations"),
                    "total_samples": iostat.get("total_samples"),
                    "samples": iostat.get("samples", [])
                }
            
            # Add arcstat telemetry if available
            if "arcstat_telemetry" in pool and pool["arcstat_telemetry"]:
                arcstat = pool["arcstat_telemetry"]
                pool_entry["arcstat_telemetry"] = {
                    "pool_name": arcstat.get("pool_name"),
                    "start_time": arcstat.get("start_time"),
                    "start_time_iso": arcstat.get("start_time_iso"),
                    "end_time": arcstat.get("end_time"),
                    "end_time_iso": arcstat.get("end_time_iso"),
                    "duration_seconds": arcstat.get("duration_seconds"),
                    "warmup_iterations": arcstat.get("warmup_iterations"),
                    "cooldown_iterations": arcstat.get("cooldown_iterations"),
                    "total_samples": arcstat.get("total_samples"),
                    "sample_interval": arcstat.get("sample_interval"),
                    "fields": arcstat.get("fields", []),
                    "samples": arcstat.get("samples", [])
                }
            
            # Add DWPD info if available
            if "dwpd" in pool:
                pool_entry["dwpd"] = round(pool["dwpd"], 2)
                pool_entry["total_writes_gib"] = round(pool["total_writes_gib"], 2)
            
            transformed_results["pools"].append(pool_entry)
        
        # Process disks
        disk_bench_dict = {}
        for disk_bench in results.get("disk_benchmark", []):
            disk_bench_dict[disk_bench.get("disk", "N/A")] = disk_bench
        
        pool_membership = results.get("pool_membership", {})
        for disk in results.get("disks", []):
            disk_entry = {
                "name": disk.get("name", "N/A"),
                "model": disk.get("model", "N/A"),
                "serial": disk.get("serial", "N/A"),
                "zfs_guid": disk.get("zfs_guid", "N/A"),
                "pool": pool_membership.get(disk.get("zfs_guid"), "N/A"),
                "size_gib": round((disk.get("size", 0) or 0) / (1024 ** 3), 2)
            }
            
            # Add benchmark if available
            if disk.get("name") in disk_bench_dict:
                bench = disk_bench_dict[disk["name"]]
                disk_entry["benchmark"] = {
                    "speeds": [round(s, 2) for s in bench.get("speeds", [])],
                    "average_speed": round(bench.get("average_speed", 0), 2),
                    "iterations": bench.get("iterations", 0)
                }
            
            transformed_results["disks"].append(disk_entry)
        
        # Write transformed results
        with open(output_path, 'w') as f:
            json.dump(transformed_results, f, indent=2)
        print_success(f"Benchmark results saved to: {os.path.abspath(output_path)}")
    except Exception as e:
        print_error(f"Error saving results to JSON: {str(e)}")
