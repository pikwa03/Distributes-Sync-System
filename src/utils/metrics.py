"""Metrics collection for monitoring system performance"""
import time
from typing import Dict, List
from collections import defaultdict, deque
from prometheus_client import Counter, Histogram, Gauge
import asyncio

class MetricsCollector:
    """Collect and expose system metrics"""
    
    def __init__(self):
        # Prometheus metrics
        self.request_counter = Counter(
            'distributed_requests_total',
            'Total number of requests',
            ['operation', 'status']
        )
        
        self.latency_histogram = Histogram(
            'distributed_operation_latency_seconds',
            'Operation latency in seconds',
            ['operation']
        )
        
        self.active_nodes = Gauge(
            'distributed_active_nodes',
            'Number of active nodes in cluster'
        )
        
        self.cache_hits = Counter(
            'cache_hits_total',
            'Total cache hits'
        )
        
        self.cache_misses = Counter(
            'cache_misses_total',
            'Total cache misses'
        )
        
        # Internal metrics
        self._latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._throughput: Dict[str, int] = defaultdict(int)
        self._start_time = time.time()
    
    def record_request(self, operation: str, status: str):
        """Record a request"""
        self.request_counter.labels(operation=operation, status=status).inc()
        self._throughput[operation] += 1
    
    def record_latency(self, operation: str, latency: float):
        """Record operation latency"""
        self.latency_histogram.labels(operation=operation).observe(latency)
        self._latencies[operation].append(latency)
    
    def record_cache_hit(self):
        """Record cache hit"""
        self.cache_hits.inc()
    
    def record_cache_miss(self):
        """Record cache miss"""
        self.cache_misses.inc()
    
    def update_active_nodes(self, count: int):
        """Update active nodes count"""
        self.active_nodes.set(count)
    
    def get_average_latency(self, operation: str) -> float:
        """Get average latency for operation"""
        if operation in self._latencies and len(self._latencies[operation]) > 0:
            return sum(self._latencies[operation]) / len(self._latencies[operation])
        return 0.0
    
    def get_throughput(self, operation: str) -> float:
        """Get throughput for operation (requests per second)"""
        elapsed = time.time() - self._start_time
        if elapsed > 0:
            return self._throughput[operation] / elapsed
        return 0.0
    
    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        hits = self.cache_hits._value.get()
        misses = self.cache_misses._value.get()
        total = hits + misses
        if total > 0:
            return hits / total
        return 0.0
    
    def get_summary(self) -> Dict:
        """Get metrics summary"""
        return {
            'uptime': time.time() - self._start_time,
            'cache_hit_rate': self.get_cache_hit_rate(),
            'operations': {
                op: {
                    'throughput': self.get_throughput(op),
                    'avg_latency': self.get_average_latency(op)
                }
                for op in self._throughput.keys()
            }
        }

# Global metrics collector instance
metrics = MetricsCollector()
