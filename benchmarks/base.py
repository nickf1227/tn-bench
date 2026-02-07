"""
Base class for tn-bench benchmarks.
All benchmarks must inherit from this class.
"""

from abc import ABC, abstractmethod


class BenchmarkBase(ABC):
    """Abstract base class for all tn-bench benchmarks."""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def validate(self) -> bool:
        """
        Check if prerequisites are met for this benchmark.
        
        Returns:
            bool: True if benchmark can run, False otherwise.
        """
        pass
    
    @abstractmethod
    def run(self, config: dict) -> dict:
        """
        Execute the benchmark.
        
        Args:
            config: Configuration dictionary with benchmark parameters.
            
        Returns:
            dict: Benchmark results.
        """
        pass
    
    @property
    @abstractmethod
    def space_required_gib(self) -> int:
        """
        Get the space required for this benchmark in GiB.
        
        Returns:
            int: Space required in GiB.
        """
        pass
