"""Performance tests for throughput"""
import pytest
import asyncio
import time
from src.nodes.cache_node import CacheNode
from src.nodes.queue_node import QueueNode

@pytest.mark.asyncio
async def test_cache_throughput():
    """Measure cache throughput"""
    cache = CacheNode(node_id=1, max_size=10000, policy='LRU')
    
    num_operations = 1000
    start_time = time.time()
    
    for i in range(num_operations):
        await cache.write(f'key{i}', f'value{i}', broadcast=False)
    
    elapsed = time.time() - start_time
    throughput = num_operations / elapsed
    
    print(f"\nCache write throughput: {throughput:.2f} ops/sec")
    assert throughput > 100  # At least 100 ops/sec

@pytest.mark.asyncio
async def test_queue_throughput():
    """Measure queue throughput"""
    queue = QueueNode(node_id=1, partition_count=256)
    
    num_operations = 1000
    start_time = time.time()
    
    for i in range(num_operations):
        await queue.enqueue('test_queue', f'item{i}')
    
    elapsed = time.time() - start_time
    throughput = num_operations / elapsed
    
    print(f"\nQueue enqueue throughput: {throughput:.2f} ops/sec")
    assert throughput > 100
