"""
Results analysis and anomaly detection for TN-Bench.

Analyzes benchmark results to detect performance issues, scaling problems,
and provide actionable recommendations.
"""

import json
import math
from typing import Dict, List, Any, Optional


class BenchmarkAnalyzer:
    """Analyzes TN-Bench results and generates insights."""
    
    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.issues = []
        self.recommendations = []
        self.grades = {}
    
    def analyze(self) -> Dict[str, Any]:
        """
        Run full analysis on benchmark results.
        
        Returns:
            Dictionary containing analysis results, grades, and recommendations.
        """
        # Clear any previous state
        self.issues = []
        self.recommendations = []
        self.grades = {}
        
        # Run analyses in order (pool analysis populates issues/grades)
        pool_analysis = self._analyze_pools()
        disk_analysis = self._analyze_disks()
        
        # Deduplicate issues and recommendations
        unique_issues = list(dict.fromkeys(self.issues))
        unique_recommendations = list(dict.fromkeys(self.recommendations))
        
        analysis = {
            "summary": self._generate_summary(),
            "pool_analysis": pool_analysis,
            "disk_analysis": disk_analysis,
            "scaling_analysis": self._analyze_scaling(pool_analysis),
            "issues": unique_issues,
            "recommendations": unique_recommendations,
            "overall_grade": self._calculate_overall_grade()
        }
        return analysis
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate high-level summary statistics."""
        pools = self.results.get("pools", [])
        disks = self.results.get("disks", [])
        
        summary = {
            "total_pools_tested": len(pools),
            "total_disks_tested": len(disks),
            "fastest_pool_write": None,
            "fastest_pool_read": None,
            "slowest_pool_write": None,
            "total_data_written_gib": 0
        }
        
        for pool in pools:
            if "benchmark" in pool and pool["benchmark"]:
                # Find peak write speed
                peak_write = max(b.get("average_write_speed", 0) for b in pool["benchmark"])
                peak_read = max(b.get("average_read_speed", 0) for b in pool["benchmark"])
                
                if summary["fastest_pool_write"] is None or peak_write > summary["fastest_pool_write"]["speed"]:
                    summary["fastest_pool_write"] = {"pool": pool["name"], "speed": peak_write}
                
                if summary["fastest_pool_read"] is None or peak_read > summary["fastest_pool_read"]["speed"]:
                    summary["fastest_pool_read"] = {"pool": pool["name"], "speed": peak_read}
                
                if summary["slowest_pool_write"] is None or peak_write < summary["slowest_pool_write"]["speed"]:
                    summary["slowest_pool_write"] = {"pool": pool["name"], "speed": peak_write}
            
            summary["total_data_written_gib"] += pool.get("total_writes_gib", 0)
        
        return summary
    
    def _analyze_pools(self) -> Dict[str, Dict[str, Any]]:
        """Analyze each pool's performance characteristics."""
        pool_analysis = {}
        
        for pool in self.results.get("pools", []):
            pool_name = pool.get("name", "unknown")
            benchmark_data = pool.get("benchmark", [])
            
            if not benchmark_data:
                continue
            
            analysis = {
                "grade": None,
                "scaling_efficiency": {},
                "optimal_thread_count": {},
                "bottleneck_detected": False,
                "issues": []
            }
            
            # Calculate scaling efficiency for writes
            write_efficiency = self._calculate_scaling_efficiency(benchmark_data, "write")
            analysis["scaling_efficiency"]["write"] = write_efficiency
            
            # Calculate scaling efficiency for reads
            read_efficiency = self._calculate_scaling_efficiency(benchmark_data, "read")
            analysis["scaling_efficiency"]["read"] = read_efficiency
            
            # Find optimal thread counts
            analysis["optimal_thread_count"]["write"] = self._find_optimal_threads(benchmark_data, "write")
            analysis["optimal_thread_count"]["read"] = self._find_optimal_threads(benchmark_data, "read")
            
            # Detect bottlenecks
            vdevs = pool.get("vdevs", [])
            disk_count = sum(v.get("disk_count", 0) for v in vdevs)
            
            # Check for negative scaling (performance regression with more threads)
            negative_scaling = self._detect_negative_scaling(benchmark_data)
            if negative_scaling:
                analysis["bottleneck_detected"] = True
                for issue in negative_scaling:
                    msg = f"{pool_name}: Negative scaling at {issue['threads']}T ({issue['type']})"
                    analysis["issues"].append(msg)
                    self.issues.append(msg)
                    self.recommendations.append(
                        f"Check {pool_name} ZFS recordsize and vdev configuration"
                    )
            
            # Check if scaling is abnormally low
            if write_efficiency.get("efficiency_percent", 100) < 10:
                analysis["bottleneck_detected"] = True
                msg = f"{pool_name}: Write scaling only {write_efficiency['efficiency_percent']:.1f}% efficient"
                analysis["issues"].append(msg)
                self.issues.append(msg)
                self.recommendations.append(
                    f"Investigate {pool_name} write path - possible recordsize mismatch or missing SLOG"
                )
            
            # Grade the pool
            analysis["grade"] = self._grade_pool(analysis, disk_count)
            self.grades[pool_name] = analysis["grade"]
            
            pool_analysis[pool_name] = analysis
        
        return pool_analysis
    
    def _calculate_scaling_efficiency(self, benchmark_data: List[Dict], 
                                       speed_type: str) -> Dict[str, Any]:
        """
        Calculate how well the pool scales with additional threads.
        
        Args:
            benchmark_data: List of benchmark results per thread count
            speed_type: 'write' or 'read'
        
        Returns:
            Dictionary with efficiency metrics
        """
        if not benchmark_data or len(benchmark_data) < 2:
            return {"efficiency_percent": 0, "linear_speedup": 0}
        
        # Sort by thread count
        sorted_data = sorted(benchmark_data, key=lambda x: x.get("threads", 0))
        
        single_thread = sorted_data[0]
        max_thread = sorted_data[-1]
        
        single_speed = single_thread.get(f"average_{speed_type}_speed", 0)
        max_speed = max_thread.get(f"average_{speed_type}_speed", 0)
        
        single_threads = single_thread.get("threads", 1)
        max_threads = max_thread.get("threads", single_threads)
        
        if single_speed <= 0 or max_threads <= single_threads:
            return {"efficiency_percent": 0, "linear_speedup": 0}
        
        # Theoretical linear speedup
        theoretical_speed = single_speed * (max_threads / single_threads)
        
        # Actual efficiency
        efficiency = (max_speed / theoretical_speed) * 100
        linear_speedup = max_speed / single_speed
        
        return {
            "efficiency_percent": round(efficiency, 2),
            "linear_speedup": round(linear_speedup, 2),
            "single_thread_speed": round(single_speed, 2),
            "max_thread_speed": round(max_speed, 2),
            "theoretical_max": round(theoretical_speed, 2)
        }
    
    def _find_optimal_threads(self, benchmark_data: List[Dict], 
                              speed_type: str) -> Optional[int]:
        """Find the thread count with best performance."""
        if not benchmark_data:
            return None
        
        speed_key = f"average_{speed_type}_speed"
        best_threads = None
        best_speed = 0
        
        for bench in benchmark_data:
            speed = bench.get(speed_key, 0)
            if speed > best_speed:
                best_speed = speed
                best_threads = bench.get("threads")
        
        return best_threads
    
    def _detect_negative_scaling(self, benchmark_data: List[Dict]) -> List[Dict]:
        """Detect cases where more threads = worse performance."""
        issues = []
        
        if len(benchmark_data) < 2:
            return issues
        
        sorted_data = sorted(benchmark_data, key=lambda x: x.get("threads", 0))
        
        for i in range(1, len(sorted_data)):
            prev = sorted_data[i - 1]
            curr = sorted_data[i]
            
            for speed_type in ["write", "read"]:
                prev_speed = prev.get(f"average_{speed_type}_speed", 0)
                curr_speed = curr.get(f"average_{speed_type}_speed", 0)
                
                # Flag if current is significantly worse (>20% drop)
                if prev_speed > 0 and curr_speed < prev_speed * 0.8:
                    issues.append({
                        "threads": curr.get("threads"),
                        "type": speed_type,
                        "drop_percent": round((1 - curr_speed / prev_speed) * 100, 1)
                    })
        
        return issues
    
    def _analyze_disks(self) -> Dict[str, Dict[str, Any]]:
        """Analyze individual disk performance."""
        disk_analysis = {}
        
        disks = self.results.get("disks", [])
        if not disks:
            return disk_analysis
        
        # Calculate average speed across all disks for comparison
        speeds = []
        for disk in disks:
            bench = disk.get("benchmark", {})
            avg = bench.get("average_speed", 0)
            if avg > 0:
                speeds.append(avg)
        
        if not speeds:
            return disk_analysis
        
        avg_speed = sum(speeds) / len(speeds)
        
        for disk in disks:
            disk_name = disk.get("name", "unknown")
            bench = disk.get("benchmark", {})
            avg = bench.get("average_speed", 0)
            
            analysis = {
                "average_speed": round(avg, 2),
                "vs_pool_average": None,
                "variance_percent": None
            }
            
            if avg > 0 and avg_speed > 0:
                variance = ((avg - avg_speed) / avg_speed) * 100
                analysis["variance_percent"] = round(variance, 1)
                analysis["vs_pool_average"] = "above" if variance > 5 else "below" if variance < -5 else "normal"
                
                # Flag outliers
                if abs(variance) > 15:
                    msg = f"{disk_name}: {variance:+.1f}% variance from average"
                    self.issues.append(msg)
            
            disk_analysis[disk_name] = analysis
        
        return disk_analysis
    
    def _analyze_scaling(self, pool_analysis: Dict) -> Dict[str, Any]:
        """Analyze overall system scaling characteristics."""
        scaling = {
            "pools_with_good_scaling": [],
            "pools_with_poor_scaling": [],
            "scaling_recommendations": []
        }
        
        for pool_name, analysis in pool_analysis.items():
            write_eff = analysis["scaling_efficiency"]["write"].get("efficiency_percent", 0)
            read_eff = analysis["scaling_efficiency"]["read"].get("efficiency_percent", 0)
            
            if write_eff > 30 or read_eff > 50:
                scaling["pools_with_good_scaling"].append(pool_name)
            else:
                scaling["pools_with_poor_scaling"].append(pool_name)
                scaling["scaling_recommendations"].append(
                    f"{pool_name}: Consider ZFS tuning (recordsize, SLOG, or vdev layout)"
                )
        
        return scaling
    
    def _grade_pool(self, analysis: Dict, disk_count: int) -> str:
        """Assign a letter grade to pool performance."""
        issues = len(analysis.get("issues", []))
        write_eff = analysis["scaling_efficiency"]["write"].get("efficiency_percent", 0)
        read_eff = analysis["scaling_efficiency"]["read"].get("efficiency_percent", 0)
        bottleneck = analysis.get("bottleneck_detected", False)
        
        # Use best of write/read efficiency (reads often cached, skewing single-thread results)
        best_eff = max(write_eff, read_eff)
        
        # Scoring - adjusted for realistic ZFS performance
        if issues == 0 and best_eff > 35:
            return "A"
        elif issues <= 1 and best_eff > 25:
            return "B"
        elif issues <= 2 and best_eff > 15:
            return "C"
        elif not bottleneck or best_eff > 10:
            return "D"
        else:
            return "F"
    
    def _calculate_overall_grade(self) -> str:
        """Calculate overall system grade from individual pool grades."""
        if not self.grades:
            return "N/A"
        
        grade_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        total = sum(grade_values.get(g, 0) for g in self.grades.values())
        avg = total / len(self.grades)
        
        reverse_map = {4: "A", 3: "B", 2: "C", 1: "D", 0: "F"}
        return reverse_map.get(round(avg), "C")


def analyze_results_file(json_path: str) -> Dict[str, Any]:
    """
    Convenience function to analyze a TN-Bench results file.
    
    Args:
        json_path: Path to the JSON results file
    
    Returns:
        Analysis dictionary
    """
    with open(json_path, 'r') as f:
        results = json.load(f)
    
    analyzer = BenchmarkAnalyzer(results)
    return analyzer.analyze()


def save_analysis_to_json(analysis: Dict[str, Any], output_path: str):
    """Save analysis results to a JSON file."""
    with open(output_path, 'w') as f:
        json.dump(analysis, f, indent=2)


# For testing/direct execution
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python analysis.py <results.json>")
        sys.exit(1)
    
    results_file = sys.argv[1]
    analysis = analyze_results_file(results_file)
    
    print(json.dumps(analysis, indent=2))
