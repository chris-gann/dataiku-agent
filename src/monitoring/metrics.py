"""
Metrics collection for Dataiku Agent.

This module provides metrics collection and export functionality
for monitoring application performance and usage.
"""
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, List

from ..core.config import Config
from ..core.logging import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """Collects and exports application metrics."""
    
    def __init__(self, config: Config):
        self.config = config
        
        # Counters
        self.counters: Dict[str, int] = defaultdict(int)
        
        # Gauges
        self.gauges: Dict[str, float] = defaultdict(float)
        
        # Histograms (simplified - just store all values)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        
        # Start time for uptime calculation
        self.start_time = time.time()
    
    def increment_counter(self, name: str, value: int = 1, labels: Dict[str, str] = None):
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        self.counters[key] += value
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric."""
        key = self._make_key(name, labels)
        self.gauges[key] = value
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a value for a histogram metric."""
        key = self._make_key(name, labels)
        self.histograms[key].append(value)
        
        # Keep only last 1000 values to prevent memory issues
        if len(self.histograms[key]) > 1000:
            self.histograms[key] = self.histograms[key][-1000:]
    
    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Create a unique key for a metric with labels."""
        if not labels:
            return name
        
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        # Add metadata
        lines.append(f"# Generated at {datetime.utcnow().isoformat()}Z")
        lines.append("")
        
        # Export uptime
        uptime = time.time() - self.start_time
        lines.append("# HELP dataiku_agent_uptime_seconds Uptime in seconds")
        lines.append("# TYPE dataiku_agent_uptime_seconds gauge")
        lines.append(f"dataiku_agent_uptime_seconds {uptime:.2f}")
        lines.append("")
        
        # Export counters
        for key, value in self.counters.items():
            metric_name = key.split("{")[0]
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f"{key} {value}")
        
        if self.counters:
            lines.append("")
        
        # Export gauges
        for key, value in self.gauges.items():
            metric_name = key.split("{")[0]
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f"{key} {value}")
        
        if self.gauges:
            lines.append("")
        
        # Export histograms (simplified - just count and sum)
        for key, values in self.histograms.items():
            if not values:
                continue
            
            metric_name = key.split("{")[0]
            count = len(values)
            total = sum(values)
            
            lines.append(f"# TYPE {metric_name} histogram")
            lines.append(f"{metric_name}_count{key[len(metric_name):]} {count}")
            lines.append(f"{metric_name}_sum{key[len(metric_name):]} {total:.2f}")
            
            # Add some basic percentiles
            sorted_values = sorted(values)
            for percentile in [0.5, 0.9, 0.99]:
                index = int(len(sorted_values) * percentile)
                if index < len(sorted_values):
                    value = sorted_values[index]
                    lines.append(
                        f'{metric_name}_percentile{key[len(metric_name):]}'
                        f',percentile="{percentile}" {value:.2f}'
                    )
        
        return "\n".join(lines)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        summary = {
            "uptime_seconds": time.time() - self.start_time,
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {}
        }
        
        # Summarize histograms
        for key, values in self.histograms.items():
            if values:
                summary["histograms"][key] = {
                    "count": len(values),
                    "sum": sum(values),
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }
        
        return summary


class MetricsExporter:
    """Exports metrics to external systems."""
    
    def __init__(self, config: Config, collector: MetricsCollector):
        self.config = config
        self.collector = collector
    
    def export_to_statsd(self, host: str, port: int):
        """Export metrics to StatsD (placeholder for future implementation)."""
        # This would send metrics to StatsD
        # For now, just log that we would export
        logger.info(
            "would_export_to_statsd",
            host=host,
            port=port,
            metrics_count=len(self.collector.counters) + len(self.collector.gauges)
        )
    
    def export_to_cloudwatch(self):
        """Export metrics to AWS CloudWatch (placeholder for future implementation)."""
        # This would send metrics to CloudWatch
        # For now, just log that we would export
        logger.info(
            "would_export_to_cloudwatch",
            metrics_count=len(self.collector.counters) + len(self.collector.gauges)
        ) 