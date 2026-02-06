"""
TN-Bench Analytics Module
Provides automated analysis and insights from benchmark results.
Part of TN-Bench 2.1
"""

import json
import math
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    """Severity levels for analysis findings."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Finding:
    """A single analysis finding."""
    severity: Severity
    category: str
    message: str
    details: Optional[Dict[str, Any]] = None
    recommendation: Optional[str] = None


@dataclass
class PoolAnalysis:
    """Analysis results for a single pool."""
    name: str
    scaling_efficiency: Dict[str, float]  # write/read -> efficiency %
    optimal_thread_count: Dict[str, int]  # write/read -> optimal threads
    anomalies: List[Finding] = field(default_factory=list)
    grade: str = "N/A"


@dataclass
class SystemAnalysis:
    """Complete system analysis results."""
    overall_grade: str
    grade_score: float  # 0-100 numeric score
    findings: List[Finding] = field(default_factory=list)
    pool_analyses: List[PoolAnalysis] = field(default_factory=list)
    disk_consistency: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall_grade": self.overall_grade,
            "grade_score": round(self.grade_score, 1),
            "findings": [
                {
                    "severity": f.severity.value,
                    "category": f.category,
                    "message": f.message,
                    "details": f.details,
                    "recommendation": f.recommendation
                }
                for f in self.findings
            ],
            "pool_analyses": [
                {
                    "name": pa.name,
                    "scaling_efficiency": {k: round(v, 1) for k, v in pa.scaling_efficiency.items()},
                    "optimal_thread_count": pa.optimal_thread_count,
                    "anomalies": [
                        {
                            "severity": a.severity.value,
                            "category": a.category,
                            "message": a.message,
                            "recommendation": a.recommendation
                        }
                        for a in pa.anomalies
                    ],
                    "grade": pa.grade
                }
                for pa in self.pool_analyses
            ],
            "disk_consistency": self.disk_consistency,
            "recommendations": self.recommendations
        }


class ResultAnalyzer:
    """Analyzes TN-Bench results for performance insights."""
    
    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.findings: List[Finding] = []
        self.pool_analyses: List[PoolAnalysis] = []
        
    def analyze(self) -> SystemAnalysis:
        """Run full analysis on benchmark results."""
        # Analyze each pool
        for pool in self.results.get("pools", []):
            pa = self._analyze_pool(pool)
            self.pool_analyses.append(pa)
            self.findings.extend(pa.anomalies)
        
        # Analyze disk consistency
        self.disk_consistency = self._analyze_disk_consistency()
        
        # Generate overall grade
        grade, score = self._calculate_overall_grade()
        
        # Compile recommendations
        recommendations = self._generate_recommendations()
        
        return SystemAnalysis(
            overall_grade=grade,
            grade_score=score,
            findings=self.findings,
            pool_analyses=self.pool_analyses,
            disk_consistency=self.disk_consistency,
            recommendations=recommendations
        )
    
    def _analyze_pool(self, pool: Dict[str, Any]) -> PoolAnalysis:
        """Analyze a single pool's performance."""
        name = pool.get("name", "unknown")
        benchmark = pool.get("benchmark", [])
        anomalies = []
        
        if not benchmark:
            return PoolAnalysis(name=name, scaling_efficiency={}, optimal_thread_count={})
        
        # Extract write and read speeds by thread count
        thread_counts = []
        write_speeds = []
        read_speeds = []
        
        for b in benchmark:
            threads = b.get("threads", 0)
            avg_write = b.get("average_write_speed", 0)
            avg_read = b.get("average_read_speed", 0)
            thread_counts.append(threads)
            write_speeds.append(avg_write)
            read_speeds.append(avg_read)
        
        # Calculate scaling efficiency
        scaling_efficiency = {}
        optimal_threads = {}
        
        for op_name, speeds in [("write", write_speeds), ("read", read_speeds)]:
            if len(speeds) >= 2 and thread_counts[0] > 0:
                single_thread_speed = speeds[0]
                max_threads = thread_counts[-1]
                max_speed = max(speeds)
                max_idx = speeds.index(max_speed)
                
                # Scaling efficiency = actual speed / theoretical max speed
                theoretical_max = single_thread_speed * max_threads
                efficiency = (max_speed / theoretical_max * 100) if theoretical_max > 0 else 0
                scaling_efficiency[op_name] = efficiency
                
                # Optimal thread count
                optimal_threads[op_name] = thread_counts[max_idx]
                
                # Check for negative scaling (multi-thread slower than single-thread)
                for i, speed in enumerate(speeds[1:], 1):
                    if speed < single_thread_speed * 0.9 and thread_counts[i] > 1:
                        anomalies.append(Finding(
                            severity=Severity.WARNING,
                            category="scaling",
                            message=f"{op_name.capitalize()} performance drops at {thread_counts[i]} threads "
                                    f"({speed:.0f} MB/s vs {single_thread_speed:.0f} MB/s single-thread)",
                            details={
                                "thread_count": thread_counts[i],
                                "speed": speed,
                                "single_thread_speed": single_thread_speed,
                                "drop_percent": round((1 - speed/single_thread_speed) * 100, 1)
                            },
                            recommendation=f"Check ZFS recordsize on pool '{name}' - may cause read-modify-write cycles"
                        ))
                
                # Check for read speed drops at high threads
                if op_name == "read" and len(speeds) >= 3:
                    peak_speed = max(speeds[:-1])  # Exclude last point
                    final_speed = speeds[-1]
                    if peak_speed > 0 and final_speed < peak_speed * 0.7:
                        anomalies.append(Finding(
                            severity=Severity.INFO,
                            category="scaling",
                            message=f"Read speed drops {round((1 - final_speed/peak_speed) * 100)}% "
                                    f"at maximum thread count ({final_speed:.0f} vs {peak_speed:.0f} MB/s)",
                            details={
                                "peak_speed": peak_speed,
                                "final_speed": final_speed,
                                "optimal_threads": thread_counts[speeds.index(peak_speed)]
                            },
                            recommendation=f"Consider limiting read threads to {thread_counts[speeds.index(peak_speed)]} for pool '{name}'"
                        ))
        
        # Calculate pool grade
        grade = self._calculate_pool_grade(scaling_efficiency, anomalies)
        
        return PoolAnalysis(
            name=name,
            scaling_efficiency=scaling_efficiency,
            optimal_thread_count=optimal_threads,
            anomalies=anomalies,
            grade=grade
        )
    
    def _analyze_disk_consistency(self) -> Dict[str, Any]:
        """Analyze consistency across all disks."""
        disks = self.results.get("disks", [])
        if not disks:
            return {}
        
        # Group disks by pool
        pools = {}
        outliers = []
        
        for disk in disks:
            pool = disk.get("pool", "N/A")
            if pool not in pools:
                pools[pool] = []
            pools[pool].append(disk)
        
        # Check for outliers within each pool
        for pool_name, pool_disks in pools.items():
            if pool_name == "N/A" or len(pool_disks) < 2:
                continue
            
            speeds = [d.get("benchmark", {}).get("average_speed", 0) for d in pool_disks]
            avg_speed = sum(speeds) / len(speeds)
            
            for disk in pool_disks:
                speed = disk.get("benchmark", {}).get("average_speed", 0)
                deviation = abs(speed - avg_speed) / avg_speed if avg_speed > 0 else 0
                
                if deviation > 0.15:  # >15% deviation
                    outliers.append({
                        "disk": disk.get("name"),
                        "pool": pool_name,
                        "speed": round(speed, 1),
                        "pool_avg": round(avg_speed, 1),
                        "deviation_percent": round(deviation * 100, 1)
                    })
                    
                    self.findings.append(Finding(
                        severity=Severity.WARNING,
                        category="disk_consistency",
                        message=f"Disk {disk.get('name')} in pool '{pool_name}' is "
                                f"{round(deviation * 100)}% slower than pool average",
                        details={
                            "disk_speed": speed,
                            "pool_average": avg_speed,
                            "model": disk.get("model", "unknown")
                        },
                        recommendation="Check for thermal throttling or drive health issues"
                    ))
        
        return {
            "pool_count": len([p for p in pools if p != "N/A"]),
            "total_disks": len(disks),
            "outliers": outliers,
            "consistency_grade": "A" if not outliers else "B" if len(outliers) <= 1 else "C"
        }
    
    def _calculate_pool_grade(self, scaling_efficiency: Dict[str, float], 
                               anomalies: List[Finding]) -> str:
        """Calculate letter grade for a pool."""
        # Base score from scaling efficiency
        scores = []
        for eff in scaling_efficiency.values():
            if eff >= 50:
                scores.append(90 + min(eff - 50, 10))  # A range
            elif eff >= 30:
                scores.append(80 + (eff - 30))  # B range
            elif eff >= 15:
                scores.append(70 + (eff - 15))  # C range
            elif eff >= 5:
                scores.append(60 + eff)  # D range
            else:
                scores.append(50)  # F
        
        if not scores:
            return "N/A"
        
        avg_score = sum(scores) / len(scores)
        
        # Penalize for critical warnings
        critical_count = sum(1 for a in anomalies if a.severity == Severity.CRITICAL)
        warning_count = sum(1 for a in anomalies if a.severity == Severity.WARNING)
        
        avg_score -= critical_count * 15
        avg_score -= warning_count * 5
        
        # Convert to letter
        if avg_score >= 90:
            return "A"
        elif avg_score >= 80:
            return "B"
        elif avg_score >= 70:
            return "C"
        elif avg_score >= 60:
            return "D"
        else:
            return "F"
    
    def _calculate_overall_grade(self) -> tuple:
        """Calculate overall system grade."""
        if not self.pool_analyses:
            return "N/A", 0.0
        
        # Map grades to scores
        grade_scores = {"A": 95, "B": 85, "C": 75, "D": 65, "F": 50, "N/A": 0}
        
        pool_grades = [pa.grade for pa in self.pool_analyses]
        scores = [grade_scores.get(g, 0) for g in pool_grades]
        
        # Average pool scores
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # Penalize for system-wide findings
        critical_count = sum(1 for f in self.findings if f.severity == Severity.CRITICAL)
        warning_count = sum(1 for f in self.findings if f.severity == Severity.WARNING)
        
        avg_score -= critical_count * 10
        avg_score -= warning_count * 3
        
        # Clamp to 0-100
        avg_score = max(0, min(100, avg_score))
        
        # Convert back to letter
        if avg_score >= 90:
            return "A", avg_score
        elif avg_score >= 80:
            return "B", avg_score
        elif avg_score >= 70:
            return "C", avg_score
        elif avg_score >= 60:
            return "D", avg_score
        else:
            return "F", avg_score
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations."""
        recs = []
        
        # Check for recordsize issues
        for pa in self.pool_analyses:
            write_eff = pa.scaling_efficiency.get("write", 100)
            if write_eff < 10:
                recs.append(
                    f"Pool '{pa.name}': Check ZFS recordsize. Low write scaling suggests "
                    "read-modify-write cycles with large block workloads."
                )
        
        # Check for optimal thread tuning
        for pa in self.pool_analyses:
            for op, threads in pa.optimal_thread_count.items():
                max_threads = max(pa.optimal_thread_count.values()) if pa.optimal_thread_count else 0
                if threads < max_threads:
                    recs.append(
                        f"Pool '{pa.name}': Limit {op} threads to {threads} for optimal throughput"
                    )
        
        # Add findings recommendations
        for finding in self.findings:
            if finding.recommendation and finding.recommendation not in recs:
                recs.append(finding.recommendation)
        
        return list(dict.fromkeys(recs))  # Remove duplicates while preserving order


def analyze_results_file(filepath: str) -> Optional[SystemAnalysis]:
    """Analyze a TN-Bench results JSON file."""
    try:
        with open(filepath, 'r') as f:
            results = json.load(f)
        
        analyzer = ResultAnalyzer(results)
        return analyzer.analyze()
    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        print(f"Error analyzing results: {e}")
        return None


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        analysis = analyze_results_file(sys.argv[1])
        if analysis:
            print(json.dumps(analysis.to_dict(), indent=2))
    else:
        print("Usage: python analytics.py <results_file.json>")
