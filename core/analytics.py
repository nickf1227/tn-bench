"""
TN-Bench Analytics Module - Neutral Data Presentation
Part of TN-Bench 2.1
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class Observation:
    """A neutral observation about benchmark behavior."""
    category: str
    description: str
    data: Optional[Dict[str, Any]] = None


@dataclass
class PoolAnalysis:
    """Analysis results for a single pool."""
    name: str
    write_scaling: Dict[str, Any]
    read_scaling: Dict[str, Any]
    observations: List[Observation] = field(default_factory=list)


@dataclass
class SystemAnalysis:
    """Complete system analysis results."""
    pool_analyses: List[PoolAnalysis] = field(default_factory=list)
    disk_comparison: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pool_analyses": [
                {
                    "name": pa.name,
                    "write_scaling": pa.write_scaling,
                    "read_scaling": pa.read_scaling,
                    "observations": [
                        {"category": o.category, "description": o.description, "data": o.data}
                        for o in pa.observations
                    ]
                }
                for pa in self.pool_analyses
            ],
            "disk_comparison": self.disk_comparison
        }


class ResultAnalyzer:
    """Analyzes TN-Bench results with neutral data presentation."""

    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.pool_analyses: List[PoolAnalysis] = []

    def analyze(self) -> SystemAnalysis:
        """Run analysis on benchmark results."""
        for pool in self.results.get("pools", []):
            pa = self._analyze_pool(pool)
            self.pool_analyses.append(pa)

        disk_comparison = self._analyze_disks()

        return SystemAnalysis(
            pool_analyses=self.pool_analyses,
            disk_comparison=disk_comparison
        )

    def _analyze_pool(self, pool: Dict[str, Any]) -> PoolAnalysis:
        """Analyze a single pool's scaling behavior."""
        name = pool.get("name", "unknown")
        benchmark = pool.get("benchmark", [])
        observations = []

        if not benchmark:
            return PoolAnalysis(
                name=name,
                write_scaling={},
                read_scaling={},
                observations=[]
            )

        # Extract data points
        thread_counts = []
        write_speeds = []
        read_speeds = []

        for b in benchmark:
            thread_counts.append(b.get("threads", 0))
            write_speeds.append(b.get("average_write_speed", 0))
            read_speeds.append(b.get("average_read_speed", 0))

        # Analyze each operation type
        write_scaling = self._analyze_scaling("write", thread_counts, write_speeds, observations, name)
        read_scaling = self._analyze_scaling("read", thread_counts, read_speeds, observations, name)

        return PoolAnalysis(
            name=name,
            write_scaling=write_scaling,
            read_scaling=read_scaling,
            observations=observations
        )

    def _analyze_scaling(self, op_name: str, threads: List[int], speeds: List[float],
                         observations: List[Observation], pool_name: str) -> Dict[str, Any]:
        """Analyze scaling behavior for one operation type."""
        if len(speeds) < 2:
            return {}

        # Build progression table
        progression = []
        for i, (t, s) in enumerate(zip(threads, speeds)):
            progression.append({
                "threads": t,
                "speed_mbps": round(s, 1),
                "vs_single_thread": round(s / speeds[0], 2) if speeds[0] > 0 else 0
            })

        # Calculate deltas between consecutive points
        deltas = []
        for i in range(1, len(speeds)):
            delta = speeds[i] - speeds[i-1]
            pct_change = (delta / speeds[i-1] * 100) if speeds[i-1] > 0 else 0
            deltas.append({
                "from_threads": threads[i-1],
                "to_threads": threads[i],
                "delta_mbps": round(delta, 1),
                "pct_change": round(pct_change, 1)
            })

        # Find peak performance
        max_speed = max(speeds)
        max_idx = speeds.index(max_speed)
        optimal_threads = threads[max_idx]

        # Calculate thread efficiency (speed per thread at peak)
        thread_efficiency = max_speed / optimal_threads if optimal_threads > 0 else 0

        # Identify transitions
        positive_transitions = [d for d in deltas if d["delta_mbps"] > 0]
        negative_transitions = [d for d in deltas if d["delta_mbps"] < 0]

        # Add observations for notable transitions
        for d in deltas:
            if d["pct_change"] < -20:  # Significant drop
                observations.append(Observation(
                    category=f"{op_name}_scaling",
                    description=f"Speed decreases from {d['from_threads']} to {d['to_threads']} threads",
                    data=d
                ))
            elif d["to_threads"] > 8 and d["pct_change"] < 5 and d["delta_mbps"] > 0:
                # Diminishing returns at high thread counts
                observations.append(Observation(
                    category=f"{op_name}_scaling",
                    description=f"Diminishing returns above {d['from_threads']} threads",
                    data=d
                ))

        # Summary observation
        if negative_transitions and not positive_transitions:
            observations.append(Observation(
                category=f"{op_name}_summary",
                description="Performance does not improve with additional threads",
                data={"single_thread": speeds[0], "max_thread": speeds[-1]}
            ))

        return {
            "progression": progression,
            "deltas": deltas,
            "peak_speed_mbps": round(max_speed, 1),
            "optimal_threads": optimal_threads,
            "thread_efficiency": round(thread_efficiency, 1),
            "positive_transitions": len(positive_transitions),
            "negative_transitions": len(negative_transitions)
        }

    def _analyze_disks(self) -> Dict[str, Any]:
        """Compare disk performance within pools using pool-relative metrics."""
        disks = self.results.get("disks", [])
        if not disks:
            return {}

        # Group by pool
        pool_disks = {}
        for disk in disks:
            pool = disk.get("pool", "unassigned")
            if pool not in pool_disks:
                pool_disks[pool] = []

            speed = disk.get("benchmark", {}).get("average_speed", 0)
            pool_disks[pool].append({
                "name": disk.get("name"),
                "model": disk.get("model", "unknown"),
                "speed_mbps": round(speed, 1)
            })

        # Build pool-relative comparison tables
        pool_stats = {}
        for pool, dlist in pool_disks.items():
            if len(dlist) < 2:
                continue

            speeds = [d["speed_mbps"] for d in dlist]
            pool_avg = sum(speeds) / len(speeds)
            pool_min = min(speeds)
            pool_max = max(speeds)

            # Build per-disk comparison
            disk_table = []
            for d in dlist:
                speed = d["speed_mbps"]
                pct_of_pool = (speed / pool_avg * 100) if pool_avg > 0 else 0
                vs_fastest = (speed / pool_max * 100) if pool_max > 0 else 0

                disk_table.append({
                    "disk": d["name"],
                    "model": d["model"],
                    "speed_mbps": speed,
                    "pct_of_pool_avg": round(pct_of_pool, 1),
                    "pct_of_pool_max": round(vs_fastest, 1)
                })

            # Sort by speed
            disk_table.sort(key=lambda x: x["speed_mbps"], reverse=True)

            pool_stats[pool] = {
                "disks": disk_table,
                "pool_average_mbps": round(pool_avg, 1),
                "pool_range_mbps": round(pool_max - pool_min, 1),
                "variance_pct": round((pool_max - pool_min) / pool_avg * 100, 1) if pool_avg > 0 else 0
            }

        return pool_stats


def analyze_results_file(filepath: str) -> Optional[SystemAnalysis]:
    """Analyze a TN-Bench results JSON file."""
    try:
        with open(filepath, 'r') as f:
            results = json.load(f)

        analyzer = ResultAnalyzer(results)
        return analyzer.analyze()
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        analysis = analyze_results_file(sys.argv[1])
        if analysis:
            print(json.dumps(analysis.to_dict(), indent=2))
    else:
        print("Usage: python analytics.py <results_file.json>")
