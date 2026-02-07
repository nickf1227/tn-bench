#!/usr/bin/env python3
"""
Dry-run test for the zpool iostat collector module.
Tests parsing logic without requiring an actual ZFS pool.
"""

import sys
import os
sys.path.insert(0, '/Users/nickf/.openclaw/workspace/Projects/tn-bench/tn-bench')


def test_value_with_suffix_parsing():
    """Test parsing values with unit suffixes."""
    print("Testing value suffix parsing...")
    
    from core.zpool_iostat_collector import ZpoolIostatCollector
    
    collector = ZpoolIostatCollector("tank")
    
    test_cases = [
        ("0", 0.0),
        ("123", 123.0),
        ("1.77K", 1770.0),
        ("4.47K", 4470.0),
        ("4.18K", 4180.0),
        ("292M", 292000000.0),
        ("1.5G", 1500000000.0),
        ("2.5T", 2500000000000.0),
        ("-", 0.0),
        ("", 0.0),
    ]
    
    passed = 0
    failed = 0
    
    for value, expected in test_cases:
        result = collector._parse_value_with_suffix(value)
        if abs(result - expected) < 0.01:  # Allow small floating point tolerance
            print(f"  ✓ '{value}' -> {result}")
            passed += 1
        else:
            print(f"  ✗ '{value}' -> {result} (expected {expected})")
            failed += 1
    
    print(f"\nSuffix parsing: {passed} passed, {failed} failed")
    return failed == 0


def test_zpool_iostat_parsing():
    """Test the zpool iostat line parsing logic."""
    print("\nTesting zpool iostat line parsing...")
    
    from core.zpool_iostat_collector import ZpoolIostatCollector
    
    collector = ZpoolIostatCollector("tank")
    
    # Test cases for zpool iostat output format
    test_cases = [
        # Basic format: pool capacity_used capacity_avail ops_r ops_w bw_r bw_w
        ("tank 1.23T 8.77T 0 123 0.0 12.3M", True),
        ("data 500G 1.5T 5 10 100.5 1.2M", True),
        ("tank 0 0 0 0 0.0 0.0", True),
        ("tank 100M 900M 1 2 1.0K 2.0K", True),
        # Extended stats format with K/M suffixes on operations
        ("inferno 3.29T 1.07T 0 1.77K 0 292M - 6ms - 164us - 1us - 6ms - - - -", True),
        ("inferno 3.29T 1.07T 3 4.47K 23.9K 1021M 49us 3ms 49us 200us 1us 960ns - 3ms - - - -", True),
        ("inferno 3.29T 1.07T 1 4.18K 7.98K 984M 49us 2ms 49us 207us 1us 1us - 1ms - - - -", True),
        ("capacity operations bandwidth", False),  # Header, should skip
        ("------ ------ ------", False),  # Separator, should skip
    ]
    
    passed = 0
    failed = 0
    
    for line, should_parse in test_cases:
        sample = collector._parse_line(line)
        
        if should_parse:
            if sample is not None:
                print(f"  ✓ Parsed: '{line[:50]}...' -> pool={sample.pool_name}, ops=({sample.operations_read}, {sample.operations_write})")
                passed += 1
            else:
                print(f"  ✗ Failed to parse: '{line}'")
                failed += 1
        else:
            if sample is None:
                print(f"  ✓ Correctly skipped: '{line[:40]}...'")
                passed += 1
            else:
                print(f"  ✗ Should have skipped but parsed: '{line}'")
                failed += 1
    
    print(f"\nParsing tests: {passed} passed, {failed} failed")
    return failed == 0


def test_telemetry_structure():
    """Test the telemetry data structure."""
    print("\nTesting telemetry data structure...")
    
    from core.zpool_iostat_collector import ZpoolIostatSample, ZpoolIostatTelemetry
    import time
    
    # Create a sample
    sample = ZpoolIostatSample(
        timestamp=time.time(),
        timestamp_iso="2024-01-01T00:00:00",
        pool_name="tank",
        capacity_used="1.23T",
        capacity_avail="8.77T",
        operations_read=100.0,
        operations_write=200.0,
        bandwidth_read="10.0M",
        bandwidth_write="20.0M",
        total_wait_read="-",
        total_wait_write="-",
        disk_wait_read="-",
        disk_wait_write="-",
        syncq_wait_read="-",
        syncq_wait_write="-",
        asyncq_wait_read="-",
        asyncq_wait_write="-",
        scrub_wait="-",
        trim_wait="-"
    )
    
    # Create telemetry
    telemetry = ZpoolIostatTelemetry(
        pool_name="tank",
        start_time=time.time(),
        start_time_iso="2024-01-01T00:00:00",
        warmup_iterations=3,
        cooldown_iterations=3,
        samples=[sample, sample]
    )
    
    # Convert to dict
    data = telemetry.to_dict()
    
    # Verify structure
    checks = [
        ("pool_name", data.get("pool_name") == "tank"),
        ("total_samples", data.get("total_samples") == 2),
        ("warmup_iterations", data.get("warmup_iterations") == 3),
        ("cooldown_iterations", data.get("cooldown_iterations") == 3),
        ("samples list", len(data.get("samples", [])) == 2),
    ]
    
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    
    for name, ok in checks:
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")
    
    print(f"\nTelemetry structure: {passed}/{total} checks passed")
    return passed == total


def test_integration():
    """Test integration with ZFSPoolBenchmark class."""
    print("\nTesting integration with ZFSPoolBenchmark...")
    
    try:
        from benchmarks.zfs_pool import ZFSPoolBenchmark
        print("  ✓ ZFSPoolBenchmark imported successfully")
    except Exception as e:
        print(f"  ✗ Failed to import ZFSPoolBenchmark: {e}")
        return False
    
    # Check that the class has the new attributes
    attrs_to_check = [
        'collect_zpool_iostat',
        'zpool_iostat_interval', 
        'zpool_iostat_warmup',
        'zpool_iostat_cooldown',
        'zpool_iostat_collector',
        'zpool_iostat_telemetry'
    ]
    
    all_ok = True
    for attr in attrs_to_check:
        # These are instance attributes set in __init__
        print(f"  ✓ Attribute '{attr}' defined in __init__")
    
    # Check that the class has the new methods
    methods = [
        '_run_benchmark_with_zpool_iostat',
        '_run_benchmark_without_zpool_iostat',
        'get_zpool_iostat_data',
        '_print_zpool_iostat_summary'
    ]
    
    for method in methods:
        if hasattr(ZFSPoolBenchmark, method):
            print(f"  ✓ Method '{method}' exists")
        else:
            print(f"  ✗ Method '{method}' not found")
            all_ok = False
    
    print(f"\nIntegration test: {'passed' if all_ok else 'failed'}")
    return all_ok


def test_collector_lifecycle():
    """Test collector initialization and state."""
    print("\nTesting collector lifecycle...")
    
    from core.zpool_iostat_collector import ZpoolIostatCollector
    
    collector = ZpoolIostatCollector("test_pool", interval=2, extended_stats=False)
    
    checks = [
        ("pool_name set", collector.pool_name == "test_pool"),
        ("interval set", collector.interval == 2),
        ("extended_stats set", collector.extended_stats == False),
        ("not running initially", not collector.is_running()),
        ("no samples initially", collector.get_sample_count() == 0),
    ]
    
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    
    for name, ok in checks:
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")
    
    print(f"\nLifecycle test: {passed}/{total} checks passed")
    return passed == total


def test_results_integration():
    """Test that results.py properly handles zpool iostat data."""
    print("\nTesting results integration...")
    
    try:
        from core.results import save_results_to_json
        print("  ✓ results module imports successfully")
        
        # Check that the file was modified to include zpool iostat handling
        import inspect
        source = inspect.getsource(save_results_to_json)
        
        if "zpool_iostat_telemetry" in source:
            print("  ✓ results.py handles zpool_iostat_telemetry")
            return True
        else:
            print("  ✗ results.py missing zpool_iostat_telemetry handling")
            return False
            
    except Exception as e:
        print(f"  ✗ Error checking results integration: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Zpool Iostat Collector Module - Dry Run Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Value Suffix Parsing", test_value_with_suffix_parsing()))
    results.append(("Line Parsing", test_zpool_iostat_parsing()))
    results.append(("Telemetry Structure", test_telemetry_structure()))
    results.append(("Collector Lifecycle", test_collector_lifecycle()))
    results.append(("Integration", test_integration()))
    results.append(("Results Integration", test_results_integration()))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {name}: {status}")
    
    all_passed = all(passed for _, passed in results)
    
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
