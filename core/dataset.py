"""
Dataset management for tn-bench.
Handles creation, deletion, and space validation of test datasets.
"""

import subprocess
import json
import os
from utils import print_info, print_success, print_error, print_warning, color_text


def get_datasets():
    """Helper function to get all datasets."""
    result = subprocess.run(['midclt', 'call', 'pool.dataset.query'], 
                            capture_output=True, text=True)
    if result.returncode == 0:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return []


def create_dataset(pool_name, recordsize="1M"):
    """
    Create a test dataset in the specified pool.
    
    Args:
        pool_name: Name of the pool to create the dataset in.
        recordsize: ZFS record size for the dataset (e.g., '1M', '128k').
                    Must match the dd block size for optimal benchmark results.
    
    Returns:
        str: Mountpoint of the created dataset, or None if failed.
    """
    # Escape spaces in the pool name
    escaped_pool_name = pool_name.replace(" ", "\\ ")
    dataset_name = f"{escaped_pool_name}/tn-bench"
    # TrueNAS API requires uppercase unit suffix (K, M) not lowercase (k, m)
    recordsize_api = recordsize.upper()
    dataset_config = {
        "name": dataset_name,
        "recordsize": recordsize_api,
        "compression": "OFF",
        "sync": "DISABLED"
    }

    # Check if the dataset already exists
    result = subprocess.run(['midclt', 'call', 'pool.dataset.query'], capture_output=True, text=True)
    if result.returncode != 0:
        print_error(f"Error querying datasets: {result.stderr}")
        return None

    existing_datasets = json.loads(result.stdout)
    dataset_exists = any(ds['name'] == dataset_name for ds in existing_datasets)

    if not dataset_exists:
        result = subprocess.run(['midclt', 'call', 'pool.dataset.create', json.dumps(dataset_config)], capture_output=True, text=True)
        if result.returncode != 0:
            print_error(f"Error creating dataset {dataset_name}: {result.stderr}")
            return None
        print_success(f"Created temporary dataset: {dataset_name}")

        # Fetch the updated dataset information
        result = subprocess.run(['midclt', 'call', 'pool.dataset.query'], capture_output=True, text=True)
        if result.returncode != 0:
            print_error(f"Error querying datasets after creation: {result.stderr}")
            return None
        existing_datasets = json.loads(result.stdout)

    # Return the mountpoint of the dataset
    for ds in existing_datasets:
        if ds['name'] == dataset_name:
            print_success(f"Dataset {dataset_name} created successfully.")
            return ds['mountpoint']
    
    print_error(f"Dataset {dataset_name} was not found after creation.")
    return None


def delete_dataset(dataset_name):
    """
    Enhanced dataset deletion with verification and force option.
    
    Args:
        dataset_name: Full name of the dataset to delete (e.g., "pool/tn-bench")
    """
    escaped_dataset_name = dataset_name.replace(" ", "\\ ")
    print_info(f"Deleting dataset: {dataset_name}")
    
    # First attempt to delete normally
    result = subprocess.run(
        ['midclt', 'call', 'pool.dataset.delete', json.dumps({"id": escaped_dataset_name, "recursive": False})],
        capture_output=True, text=True
    )
    
    # Check if dataset still exists via API
    datasets = get_datasets()
    dataset_exists = any(ds['name'] == dataset_name for ds in datasets)
    
    # Check if directory exists
    mountpoint_exists = False
    for ds in datasets:
        if ds['name'] == dataset_name:
            mountpoint = ds.get('mountpoint', '')
            if mountpoint and os.path.exists(mountpoint):
                mountpoint_exists = True
                break
    
    if dataset_exists or mountpoint_exists:
        print_warning("Dataset not fully deleted. Performing diagnostics...")
        
        if mountpoint_exists:
            # Check for processes using the mountpoint
            try:
                lsof_result = subprocess.run(
                    ['lsof', mountpoint],
                    capture_output=True, text=True
                )
                if lsof_result.stdout:
                    print_warning("Processes using the dataset:")
                    print(lsof_result.stdout)
                else:
                    print_info("No processes found using lsof")
            except FileNotFoundError:
                print_warning("lsof command not available")
        
        # Offer force delete option
        force = input(color_text("Force delete dataset? (yes/no) [no]: ", "BOLD")).strip().lower()
        if force == 'yes':
            print_info("Attempting force deletion...")
            result = subprocess.run(
                ['midclt', 'call', 'pool.dataset.delete', 
                 json.dumps({"id": escaped_dataset_name, "recursive": False, "force": True})],
                capture_output=True, text=True
            )
            
            # Verify deletion after force attempt
            datasets = get_datasets()
            if any(ds['name'] == dataset_name for ds in datasets):
                print_error("Force deletion failed. Dataset still exists.")
            else:
                print_success("Dataset force deleted successfully")
        else:
            print_info("Skipping force deletion")
    else:
        print_success("Dataset deleted successfully")


def get_dataset_available_bytes(pool_name):
    """
    Get available space in the test dataset.
    
    Returns:
        int: Available bytes, or 0 if dataset not found.
    """
    dataset_name = f"{pool_name}/tn-bench"
    result = subprocess.run(['midclt', 'call', 'pool.dataset.query'], capture_output=True, text=True)
    if result.returncode != 0:
        print_error(f"Error querying datasets: {result.stderr}")
        return 0
    try:
        datasets = json.loads(result.stdout)
    except json.JSONDecodeError:
        print_error("Failed to parse dataset query result.")
        return 0
    for ds in datasets:
        if ds.get('name') == dataset_name:
            available_info = ds.get('available', {})
            parsed_bytes = available_info.get('parsed')
            if parsed_bytes is not None:
                return parsed_bytes
            value_str = available_info.get('value', '0')
            try:
                unit = value_str[-1] if value_str[-1] in {'T', 'G', 'M', 'K', 'B'} else 'B'
                numeric_part = value_str[:-1] if unit != 'B' else value_str
                numeric_value = float(numeric_part)
                unit_multipliers = {
                    'T': 1024 ** 4,
                    'G': 1024 ** 3,
                    'M': 1024 ** 2,
                    'K': 1024,
                    'B': 1
                }
                return int(numeric_value * unit_multipliers[unit])
            except (ValueError, KeyError):
                print_error(f"Invalid value for available bytes: {value_str}")
                return 0
    print_error(f"Dataset {dataset_name} not found.")
    return 0


def validate_space(pool_name, cores, iterations):
    """
    Validate that sufficient space exists for benchmarking.
    
    Args:
        pool_name: Name of the pool to check
        cores: Number of CPU cores (determines thread count)
        iterations: Number of iterations to run (not used for space calc - space is freed between iterations)
        
    Returns:
        tuple: (has_space, available_gib, required_gib)
    """
    available_bytes = get_dataset_available_bytes(pool_name)
    # Space is freed between iterations, so we only need space for one iteration
    required_bytes = 20 * cores * (1024 ** 3)
    available_gib = available_bytes / (1024 ** 3)
    required_gib = 20 * cores
    
    return available_bytes >= required_bytes, available_gib, required_gib
