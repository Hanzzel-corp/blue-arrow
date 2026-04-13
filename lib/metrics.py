#!/usr/bin/env python3
"""
Performance metrics collection for Python modules.
Provides metrics collection with Prometheus-compatible export.
"""

import json
import time
import threading
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from config import get_config
from logger import get_logger


class MetricsCollector:
    """Metrics collector for Python workers."""
    
    def __init__(self, module_id: str):
        self.module_id = module_id
        self.config = get_config()
        self.logger = get_logger(f"{module_id}_metrics")
        self.enabled = self.config.get('monitoring.enabled', False)
        
        # Metric storage
        self.counters = defaultdict(float)
        self.gauges = defaultdict(float)
        self.histograms = defaultdict(lambda: deque(maxlen=1000))
        
        # Start time
        self.start_time = time.time()
        
        # Lock for thread safety
        self.lock = threading.RLock()
        
        if self.enabled:
            self.logger.info("Metrics collector initialized", 
                           module=module_id, enabled=True)
    
    def increment_counter(self, name: str, value: float = 1, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        if not self.enabled:
            return
        
        labels = labels or {}
        key = self._create_key(name, labels)
        
        with self.lock:
            self.counters[key] += value
        
        self.logger.debug("Counter incremented",
                         metric_type="counter",
                         name=name,
                         labels=labels,
                         value=value)
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric."""
        if not self.enabled:
            return
        
        labels = labels or {}
        key = self._create_key(name, labels)
        
        with self.lock:
            self.gauges[key] = value
        
        self.logger.debug("Gauge set",
                         metric_type="gauge",
                         name=name,
                         labels=labels,
                         value=value)
    
    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a value in a histogram."""
        if not self.enabled:
            return
        
        labels = labels or {}
        key = self._create_key(name, labels)
        
        with self.lock:
            self.histograms[key].append(value)
        
        self.logger.debug("Histogram recorded",
                         metric_type="histogram",
                         name=name,
                         labels=labels,
                         value=value)
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get counter value."""
        if not self.enabled:
            return 0.0
        
        labels = labels or {}
        key = self._create_key(name, labels)
        
        with self.lock:
            return self.counters.get(key, 0.0)
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get gauge value."""
        if not self.enabled:
            return 0.0
        
        labels = labels or {}
        key = self._create_key(name, labels)
        
        with self.lock:
            return self.gauges.get(key, 0.0)
    
    def get_histogram_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[Dict[str, float]]:
        """Get histogram statistics."""
        if not self.enabled:
            return None
        
        labels = labels or {}
        key = self._create_key(name, labels)
        
        with self.lock:
            values = list(self.histograms.get(key, []))
        
        if not values:
            return None
        
        sorted_values = sorted(values)
        count = len(values)
        total = sum(values)
        
        return {
            'count': count,
            'sum': total,
            'min': sorted_values[0],
            'max': sorted_values[-1],
            'mean': total / count,
            'p50': sorted_values[int(count * 0.5)],
            'p95': sorted_values[int(count * 0.95)],
            'p99': sorted_values[int(count * 0.99)]
        }
    
    def _create_key(self, name: str, labels: Dict[str, str]) -> str:
        """Create a metric key with labels."""
        if not labels:
            return name
        
        label_str = ','.join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f'{name}{{{label_str}}}'
    
    def timer(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Context manager for timing operations."""
        return Timer(self, name, labels or {})
    
    # Domain-specific metrics
    def record_task_started(self, task_id: str, action: str) -> None:
        """Record task start."""
        self.increment_counter('tasks_started_total', labels={'action': action})
    
    def record_task_completed(self, task_id: str, action: str, duration: float) -> None:
        """Record task completion."""
        self.increment_counter('tasks_completed_total', labels={'action': action})
        self.record_histogram('task_duration_ms', duration, labels={'action': action})
    
    def record_task_failed(self, task_id: str, action: str, duration: float, error_type: str) -> None:
        """Record task failure."""
        self.increment_counter('tasks_failed_total', 
                             labels={'action': action, 'error_type': error_type})
        self.record_histogram('task_duration_ms', duration, 
                            labels={'action': action, 'status': 'failed'})
    
    def record_operation(self, operation: str, duration: float, success: bool = True) -> None:
        """Record generic operation."""
        status = 'success' if success else 'failed'
        self.increment_counter('operations_total', 
                             labels={'operation': operation, 'status': status})
        self.record_histogram('operation_duration_ms', duration, 
                            labels={'operation': operation})
    
    def record_memory_usage(self, operation: str, memory_mb: float) -> None:
        """Record memory usage."""
        self.set_gauge('memory_usage_mb', memory_mb, labels={'operation': operation})
    
    def record_error(self, error_type: str, component: str) -> None:
        """Record an error."""
        self.increment_counter('errors_total', 
                             labels={'error_type': error_type, 'component': component})
    
    def export_prometheus_format(self) -> str:
        """Export metrics in Prometheus format."""
        if not self.enabled:
            return ""
        
        output = []
        
        # Export counters
        with self.lock:
            for key, value in self.counters.items():
                base_name = key.split('{')[0]
                output.append(f'# TYPE {base_name} counter')
                output.append(f'{key} {value}')
        
        # Export gauges
        with self.lock:
            for key, value in self.gauges.items():
                base_name = key.split('{')[0]
                output.append(f'# TYPE {base_name} gauge')
                output.append(f'{key} {value}')
        
        # Export histograms
        with self.lock:
            for key, values in self.histograms.items():
                if not values:
                    continue
                
                base_name = key.split('{')[0]
                labels = key[key.find('{'):] if '{' in key else '{}'
                
                output.append(f'# TYPE {base_name} histogram')
                
                sorted_values = sorted(values)
                count = len(sorted_values)
                total = sum(sorted_values)
                
                output.append(f'{base_name}_count{labels} {count}')
                output.append(f'{base_name}_sum{labels} {total}')
                
                # Buckets (simplified - just using percentiles as buckets)
                buckets = [0.1, 0.5, 0.9, 0.95, 0.99, 1.0]
                for bucket in buckets:
                    bucket_value = sorted_values[int(bucket * (count - 1))]
                    bucket_labels = labels.replace('}', f',le="{bucket_value}"}}')
                    output.append(f'{base_name}_bucket{bucket_labels} {count}')
                
                # Infinity bucket
                inf_labels = labels.replace('}', ',le="+Infinity"}')
                output.append(f'{base_name}_bucket{inf_labels} {count}')
        
        return '\n'.join(output)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics as a dictionary."""
        if not self.enabled:
            return {}
        
        with self.lock:
            return {
                'counters': dict(self.counters),
                'gauges': dict(self.gauges),
                'histograms': {
                    key: self.get_histogram_stats(key) or {'values': list(values)}
                    for key, values in self.histograms.items()
                },
                'uptime_seconds': int(time.time() - self.start_time),
                'module': self.module_id
            }
    
    def reset(self) -> None:
        """Reset all metrics."""
        with self.lock:
            self.counters.clear()
            self.gauges.clear()
            self.histograms.clear()
        
        self.logger.info("Metrics reset", module=self.module_id)


class Timer:
    """Context manager for timing operations."""
    
    def __init__(self, collector: MetricsCollector, name: str, labels: Dict[str, str]):
        self.collector = collector
        self.name = name
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = (time.time() - self.start_time) * 1000  # Convert to ms
            success = exc_type is None
            self.collector.record_operation(self.name, duration, success)


# Global metrics collectors
_collectors: Dict[str, MetricsCollector] = {}


def get_metrics_collector(module_id: str) -> MetricsCollector:
    """Get or create a metrics collector for the specified module."""
    if module_id not in _collectors:
        _collectors[module_id] = MetricsCollector(module_id)
    return _collectors[module_id]


def record_performance(operation: str):
    """Decorator to record function performance."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            collector = get_metrics_collector(func.__module__)
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                collector.record_operation(operation, duration, True)
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                collector.record_operation(operation, duration, False)
                collector.record_error(type(e).__name__, func.__module__)
                raise
        
        return wrapper
    return decorator


# Default collector
default_metrics = get_metrics_collector("python_worker")
