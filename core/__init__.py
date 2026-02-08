"""
Core system information collection via TrueNAS API.
"""

import subprocess
import json
from utils import print_subheader, print_info, color_text

# Import zpool iostat collector for easy access
from core.zpool_iostat_collector import (
    ZpoolIostatCollector,
    ZpoolIostatSample,
    ZpoolIostatTelemetry,
    ZpoolIostatCollectorWithContext,
    calculate_zpool_iostat_summary
)

# Import arcstat collector
from core.arcstat_collector import (
    ArcstatCollector,
    ArcstatSample,
    ArcstatTelemetry,
    calculate_arcstat_summary,
    detect_l2arc
)


def get_system_info():
    """Fetch system information from TrueNAS API."""
    result = subprocess.run(['midclt', 'call', 'system.info'], capture_output=True, text=True)
    system_info = json.loads(result.stdout)
    return system_info


def print_system_info_table(system_info):
    """Display system information in a formatted table."""
    print_subheader("System Information")
    fields = [
        ("Version", system_info.get("version", "N/A")),
        ("Load Average (1m)", system_info.get("loadavg", ["N/A", "N/A", "N/A"])[0]),
        ("Load Average (5m)", system_info.get("loadavg", ["N/A", "N/A", "N/A"])[1]),
        ("Load Average (15m)", system_info.get("loadavg", ["N/A", "N/A", "N/A"])[2]),
        ("Model", system_info.get("model", "N/A")),
        ("Cores", system_info.get("cores", "N/A")),
        ("Physical Cores", system_info.get("physical_cores", "N/A")),
        ("System Product", system_info.get("system_product", "N/A")),
        ("Physical Memory (GiB)", f"{system_info.get('physmem', 0) / (1024 ** 3):.2f}")
    ]

    max_field_length = max(len(field[0]) for field in fields)
    max_value_length = max(len(str(field[1])) for field in fields)

    # Print table header
    print(color_text(f"{'Field'.ljust(max_field_length)} | {'Value'.ljust(max_value_length)}", "BOLD"))
    print(color_text(f"{'-' * max_field_length}-+-{'-' * max_value_length}", "GREEN"))
    
    # Print table rows
    for field, value in fields:
        print(f"{color_text(field.ljust(max_field_length), 'CYAN')} | {str(value).ljust(max_value_length)}")


def get_pool_info():
    """Fetch pool information from TrueNAS API."""
    result = subprocess.run(['midclt', 'call', 'pool.query'], capture_output=True, text=True)
    pool_info = json.loads(result.stdout)
    return pool_info


def print_pool_info_table(pool_info):
    """Display pool information in formatted tables."""
    for pool in pool_info:
        print_subheader("Pool Information")
        fields = [
            ("Name", pool.get("name", "N/A")),
            ("Path", pool.get("path", "N/A")),
            ("Status", pool.get("status", "N/A"))
        ]

        topology = pool.get("topology", {})
        data = topology.get("data", []) if topology else []

        vdev_count = len(data)
        disk_count = sum(len(vdev.get("children", [])) for vdev in data)

        fields.append(("VDEV Count", vdev_count))
        fields.append(("Disk Count", disk_count))

        max_field_length = max(len(field[0]) for field in fields)
        max_value_length = max(len(str(field[1])) for field in fields)

        # Print table header
        print(color_text(f"{'Field'.ljust(max_field_length)} | {'Value'.ljust(max_value_length)}", "BOLD"))
        print(color_text(f"{'-' * max_field_length}-+-{'-' * max_value_length}", "GREEN"))
        
        # Print table rows
        for field, value in fields:
            print(f"{color_text(field.ljust(max_field_length), 'CYAN')} | {str(value).ljust(max_value_length)}")

        # Print VDEV table
        print()
        print(color_text("VDEV Name  | Type           | Disk Count", "BOLD"))
        print(color_text("-----------+----------------+---------------", "GREEN"))
        
        for vdev in data:
            vdev_name = vdev.get("name", "N/A")
            vdev_type = vdev.get("type", "N/A")
            vdev_disk_count = len(vdev.get("children", []))
            print(f"{vdev_name.ljust(11)} | {vdev_type.ljust(14)} | {vdev_disk_count}")


def get_disk_info():
    """Fetch disk information from TrueNAS API."""
    result = subprocess.run(['midclt', 'call', 'disk.query'], capture_output=True, text=True)
    disk_info = json.loads(result.stdout)
    return disk_info


def get_pool_membership():
    """Build a mapping of disk GUIDs to pool names."""
    result = subprocess.run(['midclt', 'call', 'pool.query'], capture_output=True, text=True)
    pool_info = json.loads(result.stdout)
    pool_membership = {}
    for pool in pool_info:
        topology = pool.get("topology", {})
        data = topology.get("data", []) if topology else []
        for vdev in data:
            for disk in vdev.get("children", []):
                pool_membership[disk["guid"]] = pool["name"]
    return pool_membership


def print_disk_info_table(disk_info, pool_membership):
    """Display disk information in a formatted table."""
    print_subheader("Disk Information")
    print_info("The TrueNAS API returns N/A for the Pool for boot devices and disks not in a pool.")
    
    fields = ["Name", "Model", "Serial", "ZFS GUID", "Pool", "Size (GiB)"]
    max_field_length = max(len(field) for field in fields)
    
    # Calculate max value length
    max_value_length = 0
    for disk in disk_info:
        for field in fields:
            value = str(disk.get(field.lower(), "N/A"))
            if len(value) > max_value_length:
                max_value_length = len(value)

    # Print table header
    print(color_text(f"{'Field'.ljust(max_field_length)} | {'Value'.ljust(max_value_length)}", "BOLD"))
    print(color_text(f"{'-' * max_field_length}-+-{'-' * max_value_length}", "GREEN"))
    
    # Print table rows
    for disk in disk_info:
        pool_name = pool_membership.get(disk.get("zfs_guid"), "N/A")
        size_gib = (disk.get("size", 0) or 0) / (1024 ** 3)
        values = [
            disk.get("name", "N/A"),
            disk.get("model", "N/A"),
            disk.get("serial", "N/A"),
            disk.get("zfs_guid", "N/A"),
            pool_name,
            f"{size_gib:.2f}"
        ]
        
        for i, (field, value) in enumerate(zip(fields, values)):
            field_text = color_text(field.ljust(max_field_length), "CYAN")
            print(f"{field_text} | {str(value).ljust(max_value_length)}")
        
        # Print separator between disks
        print(color_text(f"{'-' * max_field_length}-+-{'-' * max_value_length}", "GREEN"))
