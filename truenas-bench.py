#!/usr/bin/env python3
"""
tn-bench v2.3 - TrueNAS System Benchmark

Modular architecture with core functionality split into:
- utils: Common utilities and formatting
- core: System info, dataset management, results handling
- benchmarks: Individual benchmark implementations

This script serves as the user interface and coordination layer.
Supports interactive (default), unattended (--unattended), and batch (--config) modes.
"""

import argparse
import json
import os
import sys
import time
import copy

from utils import (
    print_header, print_info, print_success, print_warning, print_error, 
    print_section, print_bullet, color_text
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
from benchmarks import ZFSPoolBenchmark, EnhancedDiskBenchmark, BLOCK_SIZES, POOL_BLOCK_SIZES


# ── Lookup tables for CLI argument validation ────────────────────────────

# Valid pool block size strings (from POOL_BLOCK_SIZES values)
VALID_POOL_BLOCK_SIZES = {info["size"].upper(): info["size"] for info in POOL_BLOCK_SIZES.values()}
# e.g. {'16K': '16k', '32K': '32k', '64K': '64k', '128K': '128k', ...}

# Valid disk block size strings (from BLOCK_SIZES values)
VALID_DISK_BLOCK_SIZES = {info["size"].upper(): key for key, info in BLOCK_SIZES.items()}
# e.g. {'4K': '1', '32K': '2', '128K': '3', '1M': '4'}

VALID_DISK_MODES = {"serial", "parallel", "seek_stress"}


# ── Argument parsing ─────────────────────────────────────────────────────

def build_parser():
    """Build the argument parser with all CLI options."""
    parser = argparse.ArgumentParser(
        description='tn-bench v2.2 - TrueNAS System Benchmark',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
unattended mode examples:
  All pools, no disks:
    python3 truenas-bench.py --unattended --pools all --zfs-iterations 2 --disk-iterations 0 --confirm

  All disks, no pools:
    python3 truenas-bench.py --unattended --pools none --zfs-iterations 0 --disk-iterations 2 --disk-modes serial --confirm

  Specific pools with burn-in:
    python3 truenas-bench.py --unattended --pools fire,ice --zfs-iterations 5 --disk-iterations 3 --disk-modes serial,parallel --confirm

  Custom block sizes:
    python3 truenas-bench.py --unattended --pools all --zfs-iterations 2 --pool-block-size 128K --disk-iterations 1 --disk-block-size 1M --disk-modes serial --confirm
"""
    )

    parser.add_argument('--output', type=str, default='./tn_bench_results.json',
                        help='Path to output JSON file (default: ./tn_bench_results.json)')

    # Unattended mode flag
    parser.add_argument('--unattended', '--auto', action='store_true', default=False,
                        help='Enable unattended mode (skip all interactive prompts)')

    # Pool selection
    parser.add_argument('--pools', type=str, default=None,
                        help="Pool selection: 'all', 'none', or comma-separated pool names (e.g., 'fire,ice')")

    # ZFS pool benchmark options
    parser.add_argument('--zfs-iterations', type=int, default=None,
                        help='Number of ZFS pool benchmark iterations (0-100, 0=skip; default: 2)')
    parser.add_argument('--pool-block-size', type=str, default=None,
                        help='Pool benchmark block size: 16K, 32K, 64K, 128K, 256K, 512K, 1M, 2M, 4M, 8M, 16M (default: 1M)')

    # Disk benchmark options
    parser.add_argument('--disk-iterations', type=int, default=None,
                        help='Number of disk benchmark iterations (0-100, 0=skip; default: 2)')
    parser.add_argument('--disk-modes', type=str, default=None,
                        help="Disk test modes, comma-separated: serial, parallel, seek_stress (default: serial)")
    parser.add_argument('--disk-block-size', type=str, default=None,
                        help='Disk benchmark block size: 4K, 32K, 128K, 1M (default: 1M)')
    parser.add_argument('--seek-threads', type=int, default=None,
                        help='Threads per disk for seek_stress mode (1-32, default: 4)')

    # Safety confirmation
    parser.add_argument('--confirm', action='store_true', default=False,
                        help='Auto-confirm the safety prompt (required for --unattended)')

    # Dataset cleanup
    parser.add_argument('--cleanup', type=str, default=None, choices=['yes', 'no'],
                        help="Auto-answer dataset cleanup prompt: 'yes' or 'no' (default in unattended: yes)")

    # Batch/matrix config mode
    parser.add_argument('--config', type=str, default=None,
                        help='Path to JSON or YAML config file for batch/matrix testing '
                             '(mutually exclusive with --unattended individual args)')

    # Limit number of threads
    parser.add_argument('--limit', type=int, default='0',
                        help='Max threads to benchmark (default: no limit)')
    return parser


def validate_unattended_args(args):
    """Validate that all required arguments are present for unattended mode.
    
    Returns list of error messages (empty = valid).
    """
    errors = []

    # --confirm is required in unattended mode
    if not args.confirm:
        errors.append("--confirm is required in unattended mode (safety acknowledgment)")

    # --pools is required
    if args.pools is None:
        errors.append("--pools is required (use 'all', 'none', or comma-separated pool names)")

    # --zfs-iterations is required
    if args.zfs_iterations is None:
        errors.append("--zfs-iterations is required (0 to skip, 1-100 for iterations)")

    # --disk-iterations is required
    if args.disk_iterations is None:
        errors.append("--disk-iterations is required (0 to skip, 1-100 for iterations)")

    # Validate iteration ranges
    if args.zfs_iterations is not None and not (0 <= args.zfs_iterations <= 100):
        errors.append(f"--zfs-iterations must be 0-100 (got {args.zfs_iterations})")

    if args.disk_iterations is not None and not (0 <= args.disk_iterations <= 100):
        errors.append(f"--disk-iterations must be 0-100 (got {args.disk_iterations})")

    # Validate pool block size if provided
    if args.pool_block_size is not None:
        if args.pool_block_size.upper() not in VALID_POOL_BLOCK_SIZES:
            valid = ', '.join(sorted(VALID_POOL_BLOCK_SIZES.keys(), key=lambda x: _size_sort_key(x)))
            errors.append(f"--pool-block-size must be one of: {valid} (got '{args.pool_block_size}')")

    # Validate disk block size if provided
    if args.disk_block_size is not None:
        if args.disk_block_size.upper() not in VALID_DISK_BLOCK_SIZES:
            valid = ', '.join(sorted(VALID_DISK_BLOCK_SIZES.keys(), key=lambda x: _size_sort_key(x)))
            errors.append(f"--disk-block-size must be one of: {valid} (got '{args.disk_block_size}')")

    # Validate disk modes if provided
    if args.disk_modes is not None:
        modes = [m.strip().lower() for m in args.disk_modes.split(',')]
        invalid = [m for m in modes if m not in VALID_DISK_MODES]
        if invalid:
            errors.append(f"--disk-modes contains invalid mode(s): {', '.join(invalid)}. "
                          f"Valid modes: serial, parallel, seek_stress")

    # Validate seek threads
    if args.seek_threads is not None and not (1 <= args.seek_threads <= 32):
        errors.append(f"--seek-threads must be 1-32 (got {args.seek_threads})")

    # If disk iterations > 0 and disk-modes includes seek_stress, seek-threads is used (but has a default)
    # No error needed — default of 4 is applied later

    # If disk iterations == 0, disk options are ignored (no error)
    # If zfs iterations == 0, pool options are ignored (no error)

    return errors


def _size_sort_key(size_str):
    """Sort key for size strings like '4K', '1M', '128K'."""
    multipliers = {'K': 1024, 'M': 1024**2}
    s = size_str.upper().strip()
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            try:
                return int(s[:-1]) * mult
            except ValueError:
                return 0
    return 0


# ── Batch/Config mode helpers ────────────────────────────────────────────

def _load_config_file(path):
    """Load a batch config file (JSON or YAML).
    
    Auto-detects format by extension (.json, .yaml, .yml) or tries JSON then YAML.
    
    Returns:
        dict: Parsed config.
        
    Raises:
        SystemExit on parse errors.
    """
    if not os.path.isfile(path):
        print_error(f"Config file not found: {path}")
        sys.exit(1)

    with open(path, 'r') as f:
        raw = f.read()

    ext = os.path.splitext(path)[1].lower()

    # Try JSON first for .json files
    if ext == '.json':
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON in config file: {e}")
            sys.exit(1)

    # Try YAML for .yaml/.yml files
    if ext in ('.yaml', '.yml'):
        try:
            import yaml
        except ImportError:
            print_error("PyYAML is required for YAML config files: pip install pyyaml")
            sys.exit(1)
        try:
            return yaml.safe_load(raw)
        except yaml.YAMLError as e:
            print_error(f"Invalid YAML in config file: {e}")
            sys.exit(1)

    # Unknown extension — try JSON, then YAML
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        import yaml
        result = yaml.safe_load(raw)
        if isinstance(result, dict):
            return result
    except ImportError:
        pass
    except Exception:
        pass

    print_error(f"Could not parse config file as JSON or YAML: {path}")
    sys.exit(1)


def _validate_config(config):
    """Validate a batch config dict.
    
    Returns list of error messages (empty = valid).
    """
    errors = []

    if not isinstance(config, dict):
        return ["Config must be a JSON/YAML object (dict)"]

    # 'runs' is required and must be a non-empty list
    if 'runs' not in config:
        errors.append("Config missing required key: 'runs'")
    elif not isinstance(config['runs'], list):
        errors.append("'runs' must be a list")
    elif len(config['runs']) == 0:
        errors.append("'runs' list must contain at least one run")

    # Validate global section if present
    global_cfg = config.get('global', {})
    if not isinstance(global_cfg, dict):
        errors.append("'global' must be a dict")
        global_cfg = {}

    # Validate individual runs
    for i, run in enumerate(config.get('runs', [])):
        if not isinstance(run, dict):
            errors.append(f"Run {i+1}: must be a dict")
            continue
        if 'name' not in run:
            errors.append(f"Run {i+1}: missing required key 'name'")

    # Validate known field values across global + runs
    all_sections = [global_cfg] + [r for r in config.get('runs', []) if isinstance(r, dict)]
    for section in all_sections:
        label = section.get('name', 'global')

        # pool_block_size
        pbs = section.get('pool_block_size')
        if pbs is not None and pbs.upper() not in VALID_POOL_BLOCK_SIZES:
            valid = ', '.join(sorted(VALID_POOL_BLOCK_SIZES.keys(), key=lambda x: _size_sort_key(x)))
            errors.append(f"[{label}] pool_block_size must be one of: {valid} (got '{pbs}')")

        # disk_block_size
        dbs = section.get('disk_block_size')
        if dbs is not None and dbs.upper() not in VALID_DISK_BLOCK_SIZES:
            valid = ', '.join(sorted(VALID_DISK_BLOCK_SIZES.keys(), key=lambda x: _size_sort_key(x)))
            errors.append(f"[{label}] disk_block_size must be one of: {valid} (got '{dbs}')")

        # zfs_iterations
        zi = section.get('zfs_iterations')
        if zi is not None and (not isinstance(zi, int) or not (0 <= zi <= 100)):
            errors.append(f"[{label}] zfs_iterations must be 0-100 (got {zi})")

        # disk_iterations
        di = section.get('disk_iterations')
        if di is not None and (not isinstance(di, int) or not (0 <= di <= 100)):
            errors.append(f"[{label}] disk_iterations must be 0-100 (got {di})")

        # disk_modes
        dm = section.get('disk_modes')
        if dm is not None:
            modes = dm if isinstance(dm, list) else [m.strip() for m in str(dm).split(',')]
            invalid = [m for m in modes if m.lower() not in VALID_DISK_MODES]
            if invalid:
                errors.append(f"[{label}] disk_modes contains invalid mode(s): {', '.join(invalid)}")

        # seek_threads
        st = section.get('seek_threads')
        if st is not None and (not isinstance(st, int) or not (1 <= st <= 32)):
            errors.append(f"[{label}] seek_threads must be 1-32 (got {st})")

        # retry_cleanup
        rc = section.get('retry_cleanup')
        if rc is not None and (not isinstance(rc, int) or rc < 0):
            errors.append(f"[{label}] retry_cleanup must be a non-negative integer (got {rc})")

    return errors


def _merge_run_config(global_cfg, run_cfg):
    """Merge a single run config on top of global defaults.
    
    Run values take precedence over global values.
    
    Returns:
        dict: Merged config for this run.
    """
    merged = copy.deepcopy(global_cfg)
    for key, value in run_cfg.items():
        merged[key] = value
    return merged


def _robust_dataset_cleanup(dataset_name, retry_count=3, force=False, verify=True):
    """Delete a dataset with verification and retry logic.
    
    Args:
        dataset_name: Full dataset name (e.g., "pool/tn-bench")
        retry_count: Max retries on failure
        force: Use force delete
        verify: Verify deletion after each attempt
        
    Returns:
        bool: True if dataset was successfully deleted (or didn't exist)
    """
    from core.dataset import get_datasets
    import subprocess

    escaped_name = dataset_name.replace(" ", "\\ ")

    for attempt in range(1, retry_count + 1):
        # Check if dataset exists before trying
        datasets = get_datasets()
        if not any(ds['name'] == dataset_name for ds in datasets):
            print_success(f"Dataset {dataset_name} confirmed deleted.")
            return True

        print_info(f"Cleanup attempt {attempt}/{retry_count} for {dataset_name}" +
                   (" (force)" if force else ""))

        # Build delete args
        delete_opts = {"id": escaped_name, "recursive": False}
        if force:
            delete_opts["force"] = True

        result = subprocess.run(
            ['midclt', 'call', 'pool.dataset.delete', json.dumps(delete_opts)],
            capture_output=True, text=True
        )

        if not verify:
            if result.returncode == 0:
                print_success(f"Dataset {dataset_name} deleted (attempt {attempt}).")
                return True
            else:
                print_warning(f"Delete returned error (attempt {attempt}): {result.stderr.strip()}")
                continue

        # Verify deletion
        time.sleep(1)  # brief pause for API consistency
        datasets = get_datasets()
        if not any(ds['name'] == dataset_name for ds in datasets):
            print_success(f"Dataset {dataset_name} verified deleted (attempt {attempt}).")
            return True

        print_warning(f"Dataset {dataset_name} still exists after attempt {attempt}.")

        # If we haven't tried force yet and it's not the last attempt, escalate
        if not force and attempt < retry_count:
            print_info("Escalating to force delete...")
            force = True

    print_error(f"Failed to delete dataset {dataset_name} after {retry_count} attempts.")
    return False


def _pre_run_dataset_safety_check(pool_name):
    """Check if tn-bench dataset already exists before a run.
    
    If it exists, warn and attempt cleanup.
    
    Returns:
        bool: True if safe to proceed (no stale dataset blocking)
    """
    from core.dataset import get_datasets

    dataset_name = f"{pool_name}/tn-bench"
    datasets = get_datasets()
    if any(ds['name'] == dataset_name for ds in datasets):
        print_warning(f"Stale dataset found: {dataset_name} — cleaning up before run...")
        return _robust_dataset_cleanup(dataset_name, retry_count=3, force=True, verify=True)
    return True


def _extract_run_metrics(pool_info_with_bench):
    """Extract key metrics from a completed run's pool results.
    
    Returns:
        dict: Extracted metrics (peak IOPS, bandwidth, etc.)
    """
    metrics = {}
    for pool in pool_info_with_bench:
        pool_name = pool.get('name', 'unknown')
        bench_results = pool.get('benchmark_results', [])
        if not bench_results:
            continue

        # Find peak write and read speeds across thread configs
        peak_write = 0
        peak_read = 0
        peak_write_threads = 0
        peak_read_threads = 0

        for br in bench_results:
            avg_w = br.get('average_write_speed', 0)
            avg_r = br.get('average_read_speed', 0)
            if avg_w > peak_write:
                peak_write = avg_w
                peak_write_threads = br.get('threads', 0)
            if avg_r > peak_read:
                peak_read = avg_r
                peak_read_threads = br.get('threads', 0)

        metrics[pool_name] = {
            "peak_write_mbps": round(peak_write, 2),
            "peak_write_threads": peak_write_threads,
            "peak_read_mbps": round(peak_read, 2),
            "peak_read_threads": peak_read_threads,
            "dwpd": round(pool.get('dwpd', 0), 2),
            "total_writes_gib": round(pool.get('total_writes_gib', 0), 2),
            "duration_seconds": round(pool.get('benchmark_duration_seconds', 0), 2),
        }

    return metrics


def run_batch_config(args):
    """Execute batch/matrix testing from a config file.
    
    This is the main entry point for --config mode.
    """
    config = _load_config_file(args.config)

    # Validate config schema
    errors = _validate_config(config)
    if errors:
        print_error("Config file validation failed:")
        for err in errors:
            print_error(f"  • {err}")
        sys.exit(1)

    # Safety confirmation
    if not args.confirm:
        print_error("--confirm is required for batch config mode (safety acknowledgment)")
        sys.exit(1)

    global_cfg = config.get('global', {})
    runs = config.get('runs', [])
    description = config.get('description', 'Batch benchmark run')
    continue_on_error = config.get('continue_on_error', False)

    # ── Banner ───────────────────────────────────────────────────────
    show_welcome_banner()
    print_section("Batch Config Mode")
    print_info(f"Description: {description}")
    print_info(f"Total runs: {len(runs)}")
    print_info(f"Continue on error: {continue_on_error}")
    print()

    # Print run summary
    for i, run in enumerate(runs, 1):
        merged = _merge_run_config(global_cfg, run)
        print_bullet(f"Run {i}: {merged.get('name', f'run-{i}')} — "
                     f"pools={merged.get('pools', ['all'])}, "
                     f"block_size={merged.get('pool_block_size', '1M')}, "
                     f"zfs_iter={merged.get('zfs_iterations', 2)}, "
                     f"disk_iter={merged.get('disk_iterations', 0)}")

    print()
    print_success("Batch configuration validated — starting runs.")

    # ── Gather system info (once) ────────────────────────────────────
    batch_start_time = time.time()

    system_info = get_system_info()
    print_system_info_table(system_info)

    pool_info = get_pool_info()
    print_pool_info_table(pool_info)

    disk_info = get_disk_info()
    pool_membership = get_pool_membership()
    print_disk_info_table(disk_info, pool_membership)

    cores = system_info.get("cores", 1)

    # ── Execute runs sequentially ────────────────────────────────────
    batch_summary = {
        "description": description,
        "config_file": os.path.abspath(args.config),
        "start_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(batch_start_time)),
        "system_info": {
            "cpu_model": system_info.get("model", "N/A"),
            "logical_cores": cores,
            "memory_gib": round(system_info.get("physmem", 0) / (1024 ** 3), 2),
        },
        "runs": [],
        "total_runs": len(runs),
        "successful_runs": 0,
        "failed_runs": 0,
    }

    for run_idx, run_cfg in enumerate(runs, 1):
        merged = _merge_run_config(global_cfg, run_cfg)
        run_name = merged.get('name', f'run-{run_idx}')

        print_header(f"Run {run_idx} of {len(runs)}: {run_name}")

        run_record = {
            "index": run_idx,
            "name": run_name,
            "config": {k: v for k, v in merged.items() if k != 'name'},
            "status": "pending",
            "pool_metrics": {},
            "error": None,
            "duration_seconds": 0,
        }

        run_start = time.time()

        try:
            _execute_single_run(
                merged, run_idx, run_name, args,
                system_info, pool_info, disk_info, pool_membership, cores,
                run_record
            )
            run_record["status"] = "success"
            batch_summary["successful_runs"] += 1
            print_success(f"Run {run_idx} ({run_name}) completed successfully.")

        except Exception as e:
            run_record["status"] = "failed"
            run_record["error"] = str(e)
            batch_summary["failed_runs"] += 1
            print_error(f"Run {run_idx} ({run_name}) failed: {e}")

            if not continue_on_error:
                print_error("Stopping batch — continue_on_error is false.")
                run_record["duration_seconds"] = round(time.time() - run_start, 2)
                batch_summary["runs"].append(run_record)
                break

        run_record["duration_seconds"] = round(time.time() - run_start, 2)
        batch_summary["runs"].append(run_record)

    # ── Finalize batch summary ───────────────────────────────────────
    batch_end_time = time.time()
    batch_summary["end_time"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(batch_end_time))
    batch_summary["total_duration_minutes"] = round((batch_end_time - batch_start_time) / 60, 2)

    # Save batch summary
    output_base = os.path.splitext(args.output)[0]
    summary_path = f"{output_base}_batch_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(batch_summary, f, indent=2)
    print_success(f"Batch summary saved to: {os.path.abspath(summary_path)}")

    # Print final comparison table
    _print_batch_comparison(batch_summary)

    print_header("Batch Complete")
    print_success(f"Total batch time: {batch_summary['total_duration_minutes']:.2f} minutes")
    print_info(f"Successful: {batch_summary['successful_runs']} / {batch_summary['total_runs']}")
    if batch_summary['failed_runs'] > 0:
        print_error(f"Failed: {batch_summary['failed_runs']} / {batch_summary['total_runs']}")


def _execute_single_run(merged, run_idx, run_name, args,
                         system_info, pool_info, disk_info, pool_membership,
                         cores, run_record):
    """Execute a single benchmark run from batch config.
    
    This mirrors the core logic of main() but with config-driven parameters.
    """
    # ── Resolve parameters from merged config ────────────────────────
    pools_arg = merged.get('pools', ['all'])
    if isinstance(pools_arg, list):
        pools_arg = ','.join(pools_arg)

    zfs_iterations = merged.get('zfs_iterations', 2)
    disk_iterations = merged.get('disk_iterations', 0)
    pool_block_size = merged.get('pool_block_size', '1M')
    disk_block_size_str = merged.get('disk_block_size', '1M')
    disk_modes = merged.get('disk_modes', ['serial'])
    if isinstance(disk_modes, str):
        disk_modes = [m.strip() for m in disk_modes.split(',')]
    seek_threads = merged.get('seek_threads', 4)
    do_cleanup = merged.get('cleanup', True)
    verify_cleanup = merged.get('verify_cleanup', True)
    retry_cleanup = merged.get('retry_cleanup', 3)
    force_cleanup = merged.get('force_cleanup', False)

    # Normalize block sizes
    if pool_block_size.upper() in VALID_POOL_BLOCK_SIZES:
        pool_block_size = VALID_POOL_BLOCK_SIZES[pool_block_size.upper()]

    block_size_key = "4"  # default: 1M (menu key "4")
    if disk_block_size_str.upper() in VALID_DISK_BLOCK_SIZES:
        block_size_key = VALID_DISK_BLOCK_SIZES[disk_block_size_str.upper()]

    # Resolve pools
    selected_pools = resolve_pools_from_arg(pools_arg, pool_info)
    if selected_pools:
        print_info(f"Pools: {', '.join(p['name'] for p in selected_pools)}")
    else:
        print_info("No pools selected for this run.")

    print_info(f"ZFS iterations: {zfs_iterations}, Pool block size: {pool_block_size}")
    print_info(f"Disk iterations: {disk_iterations}")
    if disk_iterations > 0:
        print_info(f"Disk modes: {', '.join(disk_modes)}, Disk block size: {disk_block_size_str}")

    # ── Build per-run results dict ───────────────────────────────────
    run_results = {
        "schema_version": "1.0",
        "batch_run": {
            "name": run_name,
            "index": run_idx,
        },
        "system_info": system_info,
        "pools": copy.deepcopy(pool_info),
        "disk_benchmark": [],
        "total_benchmark_time_minutes": 0,
        "benchmark_config": {
            "selected_pools": [p['name'] for p in selected_pools],
            "disk_benchmark_run": disk_iterations > 0,
            "zfs_iterations": zfs_iterations,
            "disk_iterations": disk_iterations,
            "pool_block_size": pool_block_size,
            "unattended": True,
            "batch_mode": True,
        }
    }

    run_start_time = time.time()

    # ── ZFS pool benchmarks ──────────────────────────────────────────
    for pool in selected_pools:
        if zfs_iterations == 0:
            break

        pool_name = pool.get('name', 'N/A')
        pool_start_time = time.time()

        # Safety check: remove stale dataset if present
        if not _pre_run_dataset_safety_check(pool_name):
            print_warning(f"Could not clean stale dataset for {pool_name} — attempting to proceed anyway.")

        print_header(f"Testing Pool: {pool_name}")
        print_info(f"Creating test dataset for pool: {pool_name} (recordsize={pool_block_size})")
        dataset_path = create_dataset(pool_name, recordsize=pool_block_size)

        if dataset_path:
            has_space, available_gib, required_gib = validate_space(pool_name, cores, zfs_iterations)

            print_section("Space Verification")
            print_info(f"Available space: {available_gib:.2f} GiB")
            print_info(f"Space required:  {required_gib:.2f} GiB (20 GiB/thread × {cores} threads)")
            print_info(f"Test iterations: {zfs_iterations} (space freed between iterations)")

            if not has_space:
                print_error(f"Insufficient space in dataset {pool_name}/tn-bench")
                _robust_dataset_cleanup(f"{pool_name}/tn-bench", retry_cleanup, force_cleanup, verify_cleanup)
                continue

            print_success("Sufficient space available — proceeding with benchmarks")

            zfs_benchmark = ZFSPoolBenchmark(pool_name, cores, dataset_path, zfs_iterations, block_size=pool_block_size)
            pool_bench_results = zfs_benchmark.run()
            total_bytes_written = pool_bench_results["total_bytes_written"]

            pool_end_time = time.time()
            pool_duration = pool_end_time - pool_start_time

            pool_capacity_bytes = None
            for p in pool_info:
                if p['name'] == pool_name:
                    pool_capacity_bytes = p.get('size', 0)
                    break

            total_writes_gib = total_bytes_written / (1024 ** 3)
            pool_capacity_gib = pool_capacity_bytes / (1024 ** 3) if pool_capacity_bytes else 0
            dwpd = calculate_dwpd(total_writes_gib, pool_capacity_gib, pool_duration)

            print_section("Pool Write Summary")
            print_info(f"Total data written: {total_writes_gib:.2f} GiB")
            print_info(f"Pool capacity: {pool_capacity_gib:.2f} GiB")
            print_info(f"Benchmark duration: {pool_duration:.2f} seconds")
            print_info(f"Drive Writes Per Day (DWPD): {dwpd:.2f}")

            # Store results in the per-run results
            for pool_entry in run_results["pools"]:
                if pool_entry["name"] == pool_name:
                    pool_entry["benchmark_results"] = pool_bench_results["benchmark_results"]
                    pool_entry["total_writes_gib"] = total_writes_gib
                    pool_entry["dwpd"] = dwpd
                    pool_entry["benchmark_duration_seconds"] = pool_duration
                    iostat_telemetry = pool_bench_results.get("zpool_iostat_telemetry")
                    arcstat_telemetry = pool_bench_results.get("arcstat_telemetry")
                    if iostat_telemetry:
                        pool_entry["zpool_iostat_telemetry"] = iostat_telemetry
                    if arcstat_telemetry:
                        pool_entry["arcstat_telemetry"] = arcstat_telemetry
                    break

            zfs_benchmark.cleanup()

    # ── Disk benchmarks ──────────────────────────────────────────────
    if disk_iterations > 0:
        all_disk_results = []
        for mode in disk_modes:
            print_header("Disk Benchmark Configuration")
            print_info(f"Test mode: {mode}")
            print_info(f"Block size: {BLOCK_SIZES[block_size_key]['description']}")
            if mode == "seek_stress":
                print_info(f"Threads per disk: {seek_threads}")

            disk_benchmark = EnhancedDiskBenchmark(
                disk_info, system_info,
                test_mode=mode,
                block_size=block_size_key,
                iterations=disk_iterations,
                seek_threads=seek_threads
            )
            mode_results = disk_benchmark.run()
            all_disk_results.extend(mode_results)
        run_results["disk_benchmark"] = all_disk_results

    run_end_time = time.time()
    run_results["total_benchmark_time_minutes"] = round((run_end_time - run_start_time) / 60, 2)

    # ── Cleanup datasets ─────────────────────────────────────────────
    if do_cleanup and zfs_iterations > 0:
        for pool in selected_pools:
            pool_name = pool.get('name', 'N/A')
            dataset_name = f"{pool_name}/tn-bench"
            success = _robust_dataset_cleanup(
                dataset_name,
                retry_count=retry_cleanup,
                force=force_cleanup,
                verify=verify_cleanup
            )
            if not success:
                print_warning(f"Dataset {dataset_name} cleanup failed — continuing to next run.")

    # ── Save individual run results ──────────────────────────────────
    output_base = os.path.splitext(args.output)[0]
    run_output_path = f"{output_base}_run{run_idx}_{run_name}.json"
    save_results_to_json(run_results, run_output_path, run_start_time, run_end_time)

    # ── Run analytics for this run ───────────────────────────────────
    try:
        with open(run_output_path, 'r') as f:
            results_for_analysis = json.load(f)

        analyzer = ResultAnalyzer(results_for_analysis)
        analysis = analyzer.analyze()

        analytics_path = run_output_path.replace('.json', '_analytics.json')
        report_path = run_output_path.replace('.json', '_report.md')

        with open(analytics_path, 'w') as f:
            json.dump(analysis.to_dict(), f, indent=2)
        print_success(f"Analytics saved to: {os.path.abspath(analytics_path)}")

        report = generate_markdown_report(analysis.to_dict(), run_output_path)
        with open(report_path, 'w') as f:
            f.write(report)
        print_success(f"Report saved to: {os.path.abspath(report_path)}")

    except Exception as e:
        print_warning(f"Analytics for run {run_idx} failed (non-critical): {e}")

    # ── Extract metrics for batch summary ────────────────────────────
    run_record["pool_metrics"] = _extract_run_metrics(
        [p for p in run_results["pools"] if "benchmark_results" in p]
    )
    run_record["output_file"] = os.path.abspath(run_output_path)


def _print_batch_comparison(batch_summary):
    """Print a comparison table across all batch runs."""
    runs = batch_summary.get("runs", [])
    if not runs:
        return

    print_header("Batch Results Comparison")

    # Collect all pool names across runs
    all_pools = set()
    for run in runs:
        all_pools.update(run.get("pool_metrics", {}).keys())

    if not all_pools:
        print_info("No pool benchmark metrics to compare.")
        return

    for pool_name in sorted(all_pools):
        print_section(f"Pool: {pool_name}")

        # Table header
        header = f"{'Run':<30} {'Status':<10} {'Write MB/s':<12} {'Read MB/s':<12} {'DWPD':<8} {'Duration':<10}"
        print(color_text(header, "BOLD"))
        print(color_text("-" * len(header), "GREEN"))

        for run in runs:
            name = run.get("name", "?")[:28]
            status = run.get("status", "?")
            metrics = run.get("pool_metrics", {}).get(pool_name, {})

            if status == "success" and metrics:
                write_speed = f"{metrics.get('peak_write_mbps', 0):.1f}"
                read_speed = f"{metrics.get('peak_read_mbps', 0):.1f}"
                dwpd = f"{metrics.get('dwpd', 0):.2f}"
                duration = f"{metrics.get('duration_seconds', 0):.0f}s"
            elif status == "failed":
                write_speed = read_speed = dwpd = duration = "FAILED"
            else:
                write_speed = read_speed = dwpd = duration = "N/A"

            status_colored = color_text(status, "GREEN" if status == "success" else "RED")
            print(f"{name:<30} {status_colored:<10} {write_speed:<12} {read_speed:<12} {dwpd:<8} {duration:<10}")

    print()


def resolve_pools_from_arg(pools_arg, pool_info):
    """Resolve --pools argument to a list of pool dicts.
    
    Args:
        pools_arg: 'all', 'none', or comma-separated pool names
        pool_info: List of pool dicts from API
        
    Returns:
        list of selected pool dicts
        
    Raises:
        SystemExit on invalid pool names
    """
    if pools_arg.lower() == 'all':
        return pool_info
    if pools_arg.lower() == 'none':
        return []

    available_names = {p['name'].lower(): p for p in pool_info}
    requested = [name.strip() for name in pools_arg.split(',')]
    selected = []
    invalid = []

    for name in requested:
        if name.lower() in available_names:
            selected.append(available_names[name.lower()])
        else:
            invalid.append(name)

    if invalid:
        available_list = ', '.join(p['name'] for p in pool_info)
        print_error(f"Unknown pool(s): {', '.join(invalid)}")
        print_error(f"Available pools: {available_list}")
        sys.exit(1)

    return selected


# ── Interactive prompt functions (unchanged) ─────────────────────────────

def get_user_confirmation():
    """Display welcome message and get user confirmation to proceed."""
    print_header("tn-bench v2.2 (Modular)")
    print(color_text("tn-bench is an OpenSource Software Script that uses standard tools to", "BOLD"))
    print(color_text("Benchmark your System and collect various statistical information via", "BOLD"))
    print(color_text("the TrueNAS API.", "BOLD"))
    print()
    
    print_info("tn-bench will create a Dataset in each of your pools for testing purposes")
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
        print_info("Exiting tn-bench.")
        exit(0)


def show_welcome_banner():
    """Display welcome banner (used in both modes)."""
    print_header("tn-bench v2.2 (Modular)")
    print(color_text("tn-bench is an OpenSource Software Script that uses standard tools to", "BOLD"))
    print(color_text("Benchmark your System and collect various statistical information via", "BOLD"))
    print(color_text("the TrueNAS API.", "BOLD"))
    print()
    
    print_info("tn-bench will create a Dataset in each of your pools for testing purposes")
    print_info("that will consume 20 GiB of space for every thread in your system.")
    print()
    
    print_warning("This test will make your system EXTREMELY slow during its run.")
    print_warning("It is recommended to run this test when no other workloads are running.")
    print()
    
    print_info("ZFS ARC will impact your results. You can set zfs_arc_max to 1 to prevent ARC caching.")
    print_info("Setting it back to 0 restores default behavior but requires a system restart.")


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


def ask_pool_block_size():
    """Ask user for pool benchmark block size (synchronized with dataset recordsize)."""
    print_header("Pool Block Size Selection")
    print_info("Select the block size for pool testing:")
    print_info("This sets both the dd block size and dataset record size.")
    print()
    
    for key, info in POOL_BLOCK_SIZES.items():
        print_bullet(f"{key:>2}. {info['description']}")
    print()
    print_info("Smaller blocks test metadata-heavy workloads and IOPS.")
    print_info("Larger blocks test sequential throughput.")
    print_info("1M is the default and matches prior tn-bench behavior.")
    
    while True:
        response = input(color_text("\nEnter block size (1-11) [7]: ", "BOLD")).strip()
        if not response or response == "7":
            return POOL_BLOCK_SIZES["7"]["size"]  # Default: 1M
        elif response in POOL_BLOCK_SIZES:
            selected = POOL_BLOCK_SIZES[response]["size"]
            print_success(f"Selected pool block size: {selected}")
            return selected
        else:
            print_error("Invalid choice. Please enter a number between 1 and 11")


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


# ── Core logic ───────────────────────────────────────────────────────────

def calculate_dwpd(total_writes_gib, pool_capacity_gib, test_duration_seconds):
    """Calculate Drive Writes Per Day (DWPD)."""
    if pool_capacity_gib <= 0:
        return 0.0
    
    writes_per_second = total_writes_gib / pool_capacity_gib / test_duration_seconds
    dwpd = writes_per_second * 86400  # 86400 seconds in a day
    return dwpd


def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── Batch config mode ────────────────────────────────────────────
    if args.config:
        run_batch_config(args)
        return

    unattended = args.unattended

    # ── Validate unattended arguments ────────────────────────────────
    if unattended:
        errors = validate_unattended_args(args)
        if errors:
            print_error("Unattended mode requires the following arguments:")
            for err in errors:
                print_error(f"  • {err}")
            print()
            print_info("Example:")
            print_info("  python3 truenas-bench.py --unattended --pools all --zfs-iterations 2 "
                       "--disk-iterations 0 --confirm")
            sys.exit(1)

    benchmark_results = {
        "system_info": {},
        "pools": [],
        "disk_benchmark": [],
        "total_benchmark_time_minutes": 0,
        "benchmark_config": {
            "selected_pools": [],
            "disk_benchmark_run": False,
            "zfs_iterations": 2,
            "disk_iterations": 2,
            "unattended": unattended
        }
    }

    # ── Confirmation ─────────────────────────────────────────────────
    if unattended:
        show_welcome_banner()
        print_section("Confirmation")
        print_success("Unattended mode: --confirm flag provided, proceeding automatically.")
    else:
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

    # ── Pool selection ───────────────────────────────────────────────
    if unattended:
        selected_pools = resolve_pools_from_arg(args.pools, pool_info)
        if selected_pools:
            print_info(f"Unattended: Selected pools: {', '.join(p['name'] for p in selected_pools)}")
        else:
            print_info("Unattended: No pools selected (--pools none)")
    else:
        selected_pools = select_pools_to_test(pool_info)
    benchmark_results["benchmark_config"]["selected_pools"] = [p['name'] for p in selected_pools]
    
    # ── ZFS iterations ───────────────────────────────────────────────
    if unattended:
        zfs_iterations = args.zfs_iterations
        if zfs_iterations == 0:
            print_info("Unattended: Skipping ZFS pool benchmark (--zfs-iterations 0)")
        else:
            print_info(f"Unattended: ZFS pool iterations: {zfs_iterations}")
    else:
        zfs_iterations = ask_iteration_count("ZFS Pool")
    benchmark_results["benchmark_config"]["zfs_iterations"] = zfs_iterations
    
    # ── Pool block size ──────────────────────────────────────────────
    pool_block_size = "1M"  # default
    if zfs_iterations > 0:
        if unattended:
            if args.pool_block_size is not None:
                pool_block_size = VALID_POOL_BLOCK_SIZES[args.pool_block_size.upper()]
                print_info(f"Unattended: Pool block size: {pool_block_size}")
            else:
                print_info(f"Unattended: Pool block size: {pool_block_size} (default)")
        else:
            pool_block_size = ask_pool_block_size()
    benchmark_results["benchmark_config"]["pool_block_size"] = pool_block_size
    
    # ── Disk iterations ──────────────────────────────────────────────
    if unattended:
        disk_iterations = args.disk_iterations
        if disk_iterations == 0:
            print_info("Unattended: Skipping disk benchmark (--disk-iterations 0)")
        else:
            print_info(f"Unattended: Disk iterations: {disk_iterations}")
    else:
        disk_iterations = ask_iteration_count("Individual Disk")
    run_disk_bench = disk_iterations > 0
    benchmark_results["benchmark_config"]["disk_benchmark_run"] = run_disk_bench
    benchmark_results["benchmark_config"]["disk_iterations"] = disk_iterations
    
    # ── Disk benchmark options ───────────────────────────────────────
    disk_test_modes = ["serial"]
    block_size = "4"  # menu key — "4" maps to 1M
    seek_threads = 4
    
    if run_disk_bench:
        if unattended:
            # Disk test modes
            if args.disk_modes is not None:
                disk_test_modes = [m.strip().lower() for m in args.disk_modes.split(',')]
            print_info(f"Unattended: Disk test modes: {', '.join(disk_test_modes)}")
            
            # Disk block size
            if args.disk_block_size is not None:
                block_size = VALID_DISK_BLOCK_SIZES[args.disk_block_size.upper()]
                print_info(f"Unattended: Disk block size: {BLOCK_SIZES[block_size]['size']}")
            else:
                print_info(f"Unattended: Disk block size: {BLOCK_SIZES[block_size]['size']} (default)")
            
            # Seek threads
            if "seek_stress" in disk_test_modes:
                seek_threads = args.seek_threads if args.seek_threads is not None else 4
                print_info(f"Unattended: Seek threads: {seek_threads}")
        else:
            disk_test_modes = ask_disk_test_modes()
            block_size = ask_disk_block_size()
            if "seek_stress" in disk_test_modes:
                seek_threads = ask_seek_threads()
        
        benchmark_results["benchmark_config"]["disk_test_modes"] = disk_test_modes
        benchmark_results["benchmark_config"]["disk_block_size"] = BLOCK_SIZES[block_size]["size"]
        benchmark_results["benchmark_config"]["disk_seek_threads"] = seek_threads

    if args.limit > 0:
        cores = max(4, min(args.limit, system_info.get("cores", 1)))
    else:
        cores = system_info.get("cores", 1)

    # ── Print config summary ─────────────────────────────────────────
    print_header("DD Benchmark Starting")
    if unattended:
        print_info("Mode: UNATTENDED (all prompts skipped)")
    print_info(f"Using {cores} threads for the benchmark.")
    
    if zfs_iterations > 0:
        print_info(f"ZFS tests will run {zfs_iterations} time(s) per configuration")
    else:
        print_info("Skipping ZFS pool benchmark")
    
    if disk_iterations > 0:
        print_info(f"Disk tests will run {disk_iterations} time(s) per disk")
    else:
        print_info("Skipping individual disk benchmark")

    # ── Run ZFS pool benchmarks ──────────────────────────────────────
    for pool in selected_pools:
        if zfs_iterations == 0:
            break
            
        pool_name = pool.get('name', 'N/A')
        pool_start_time = time.time()
        print_header(f"Testing Pool: {pool_name}")
        print_info(f"Creating test dataset for pool: {pool_name} (recordsize={pool_block_size})")
        dataset_path = create_dataset(pool_name, recordsize=pool_block_size)
        
        if dataset_path:
            # Check available space
            has_space, available_gib, required_gib = validate_space(pool_name, cores, zfs_iterations)
            
            print_section("Space Verification")
            print_info(f"Available space: {available_gib:.2f} GiB")
            print_info(f"Space required:  {required_gib:.2f} GiB (20 GiB/thread × {cores} threads)")
            print_info(f"Test iterations: {zfs_iterations} (space freed between iterations)")
            
            if not has_space:
                print_error(f"Insufficient space in dataset {pool_name}/tn-bench")
                print_error(f"Minimum required: {required_gib} GiB")
                print_error(f"Available:        {available_gib:.2f} GiB")
                print_info(f"Skipping benchmarks for pool {pool_name}")
                delete_dataset(f"{pool_name}/tn-bench")
                continue

            print_success("Sufficient space available - proceeding with benchmarks")
            
            # Run ZFS pool benchmark using the modular benchmark class
            zfs_benchmark = ZFSPoolBenchmark(pool_name, cores, dataset_path, zfs_iterations, block_size=pool_block_size)
            pool_bench_results = zfs_benchmark.run()
            total_bytes_written = pool_bench_results["total_bytes_written"]
            iostat_telemetry = pool_bench_results.get("zpool_iostat_telemetry")
            arcstat_telemetry = pool_bench_results.get("arcstat_telemetry")
            
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
                    if iostat_telemetry:
                        pool_entry["zpool_iostat_telemetry"] = iostat_telemetry
                    if arcstat_telemetry:
                        pool_entry["arcstat_telemetry"] = arcstat_telemetry
                    break
            
            zfs_benchmark.cleanup()

    # ── Run disk benchmarks ──────────────────────────────────────────
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

    # ── Cleanup datasets ─────────────────────────────────────────────
    for pool in selected_pools:
        if zfs_iterations == 0:
            break
            
        pool_name = pool.get('name', 'N/A')
        dataset_name = f"{pool_name}/tn-bench"

        if unattended:
            # In unattended mode: default to cleanup unless --cleanup no
            cleanup = args.cleanup if args.cleanup is not None else 'yes'
            if cleanup == 'yes':
                delete_dataset(dataset_name)
                print_success(f"Dataset {dataset_name} deleted (unattended).")
            else:
                print_info(f"Dataset {dataset_name} not deleted (--cleanup no).")
        else:
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
    main()
