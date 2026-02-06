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
    scaling_efficiency: Dict[str, float]  # write/read -> efficiency % (backward compat)
    optimal_thread_count: Dict[str, int]  # write/read -> optimal threads
    anomalies: List[Finding] = field(default_factory=list)
    grade: str = "N/A"
    scaling_patterns: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # Detailed pattern analysis


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
                    "scaling_patterns": pa.scaling_patterns,
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
        """Analyze a single pool's performance using delta-based scaling analysis."""
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

        # Analyze scaling patterns using deltas
        scaling_analysis = {}
        optimal_threads = {}

        for op_name, speeds in [("write", write_speeds), ("read", read_speeds)]:
            if len(speeds) >= 2:
                max_speed = max(speeds)
                max_idx = speeds.index(max_speed)
                optimal_threads[op_name] = thread_counts[max_idx]

                # Calculate deltas between consecutive thread counts
                deltas = []
                marginal_gains = []  # Speed gain per thread added
                for i in range(1, len(speeds)):
                    delta = speeds[i] - speeds[i-1]
                    threads_added = thread_counts[i] - thread_counts[i-1]
                    deltas.append({
                        "from": thread_counts[i-1],
                        "to": thread_counts[i],
                        "delta": delta,
                        "pct_change": (delta / speeds[i-1] * 100) if speeds[i-1] > 0 else 0
                    })
                    if threads_added > 0:
                        marginal_gains.append(delta / threads_added)

                # Analyze scaling pattern
                positive_deltas = sum(1 for d in deltas if d["delta"] > 0)
                negative_deltas = sum(1 for d in deltas if d["delta"] < 0)
                total_deltas = len(deltas)

                # Determine scaling pattern based on progression
                final_speed = speeds[-1]
                single_thread_speed = speeds[0]
                majority_negative = negative_deltas > positive_deltas
                any_negative = negative_deltas > 0

                if majority_negative or final_speed < single_thread_speed * 0.9:
                    pattern = "regressive"  # Overall performance degrades
                elif positive_deltas == total_deltas:
                    pattern = "steady_improvement"  # Every step improves
                elif any_negative and positive_deltas > negative_deltas:
                    pattern = "peaks_early"  # Improves then falls off (like inferno)
                elif positive_deltas >= total_deltas * 0.5:
                    pattern = "mixed"
                else:
                    pattern = "plateau"

                # Calculate efficiency score based on actual gains vs thread investment
                # (what % of thread additions produced meaningful gains)
                meaningful_gains = sum(1 for d in deltas if d["pct_change"] > 10)  # >10% gain
                efficiency = (meaningful_gains / total_deltas * 100) if total_deltas > 0 else 0

                scaling_analysis[op_name] = {
                    "pattern": pattern,
                    "efficiency": efficiency,
                    "deltas": deltas,
                    "max_speed": max_speed,
                    "max_speed_threads": thread_counts[max_idx],
                    "marginal_gain_avg": sum(marginal_gains) / len(marginal_gains) if marginal_gains else 0
                }

                # Detect anomalies based on deltas
                for delta_info in deltas:
                    # Negative scaling detection
                    if delta_info["delta"] < -50:  # Lost more than 50 MB/s
                        anomalies.append(Finding(
                            severity=Severity.WARNING,
                            category="scaling_regression",
                            message=f"{op_name.capitalize()} regresses from {delta_info['from']} to {delta_info['to']} threads "
                                    f"({delta_info['delta']:+.0f} MB/s, {delta_info['pct_change']:+.1f}%)",
                            details=delta_info,
                            recommendation=f"Severe contention detected on pool '{name}' - consider thread limiting"
                        ))
                    elif delta_info["delta"] < 0:
                        anomalies.append(Finding(
                            severity=Severity.INFO,
                            category="scaling_regression",
                            message=f"{op_name.capitalize()} slight regression from {delta_info['from']} to {delta_info['to']} threads "
                                    f"({delta_info['delta']:+.0f} MB/s)",
                            details=delta_info
                        ))
                    # Diminishing returns detection
                    elif delta_info["pct_change"] < 5 and delta_info["to"] > 8:
                        anomalies.append(Finding(
                            severity=Severity.INFO,
                            category="diminishing_returns",
                            message=f"{op_name.capitalize()} shows diminishing returns at {delta_info['to']} threads "
                                    f"(only {delta_info['pct_change']:.1f}% gain)",
                            details=delta_info,
                            recommendation=f"Pool '{name}' {op_name} performance plateaus around {delta_info['from']} threads"
                        ))

        # Calculate pool grade based on patterns
        grade = self._calculate_pool_grade_v2(scaling_analysis, anomalies)

        # Extract efficiency for backward compatibility
        scaling_efficiency = {
            op: analysis["efficiency"]
            for op, analysis in scaling_analysis.items()
        }

        # Extract patterns for output
        scaling_patterns = {
            op: {
                "pattern": analysis["pattern"],
                "efficiency": round(analysis["efficiency"], 1),
                "max_speed": analysis["max_speed"],
                "max_speed_threads": analysis["max_speed_threads"],
                "marginal_gain_avg": round(analysis["marginal_gain_avg"], 2),
                "deltas": analysis["deltas"]
            }
            for op, analysis in scaling_analysis.items()
        }

        return PoolAnalysis(
            name=name,
            scaling_efficiency=scaling_efficiency,
            optimal_thread_count=optimal_threads,
            anomalies=anomalies,
            grade=grade,
            scaling_patterns=scaling_patterns
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
        """Calculate letter grade for a pool.

        Note: ZFS has inherent scaling limitations due to memory copies.
        On DDR4 platforms, 35-45% efficiency is good (B grade).
        On DDR5 platforms, expect 50-70% efficiency (A grade potential).
        """
        # Adjusted for ZFS real-world performance
        # ZFS memory copy overhead limits ideal scaling
        scores = []
        for eff in scaling_efficiency.values():
            if eff >= 60:  # Excellent - likely DDR5 or optimal config
                scores.append(90 + min(eff - 60, 10))  # A range
            elif eff >= 35:  # Good - typical for DDR4 + ZFS + NVMe
                scores.append(80 + (eff - 35))  # B range (35% = 80, 59% = 99)
            elif eff >= 20:  # Fair - some bottleneck present
                scores.append(70 + (eff - 20))  # C range
            elif eff >= 10:  # Poor - significant issue
                scores.append(60 + eff)  # D range
            else:
                scores.append(50)  # F - broken scaling

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

    def _calculate_pool_grade_v2(self, scaling_analysis: Dict[str, Dict[str, Any]],
                                  anomalies: List[Finding]) -> str:
        """Calculate letter grade based on scaling patterns and deltas.

        Focuses on:
        - Pattern type (steady_improvement > plateau > regressive)
        - Efficiency (how many thread steps produced gains)
        - Presence of negative deltas
        """
        if not scaling_analysis:
            return "N/A"

        scores = []
        for op_name, analysis in scaling_analysis.items():
            pattern = analysis.get("pattern", "unknown")
            efficiency = analysis.get("efficiency", 0)
            marginal_gain = analysis.get("marginal_gain_avg", 0)

            # Base score from pattern
            if pattern == "steady_improvement":
                base_score = 85  # B+ start
            elif pattern == "peaks_early":
                base_score = 75  # C+ start (common for ZFS, not terrible)
            elif pattern == "mixed":
                base_score = 70  # C start
            elif pattern == "plateau":
                base_score = 65  # D+ start
            elif pattern == "regressive":
                base_score = 50  # F start (actual degradation)
            else:
                base_score = 60

            # Adjust by efficiency (how many steps produced >10% gains)
            if efficiency >= 75:  # 3/4 or 4/4 steps improved
                base_score += 10
            elif efficiency >= 50:  # Half the steps improved
                base_score += 5
            elif efficiency >= 25:  # Some improvement
                base_score += 0
            else:  # Minimal improvement
                base_score -= 10

            # Bonus for good marginal gains (>50 MB/s per thread)
            if marginal_gain > 100:
                base_score += 5
            elif marginal_gain < 0:
                base_score -= 15

            scores.append(base_score)

        avg_score = sum(scores) / len(scores) if scores else 0

        # Penalize for regressions
        regression_count = sum(1 for a in anomalies
                               if a.category == "scaling_regression" and a.severity == Severity.WARNING)
        slight_regression_count = sum(1 for a in anomalies
                                      if a.category == "scaling_regression" and a.severity == Severity.INFO)

        avg_score -= regression_count * 15
        avg_score -= slight_regression_count * 5

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
