"""Unit tests for Cache Node"""
import pytest
import asyncio
from src.nodes.cache_node import CacheNode, CacheState

@pytest.mark.asyncio
async def test_cache_read_write():
    """Test basic cache read and write"""
    cache = CacheNode(node_id=1, max_size=100, policy='LRU')
    
    # Write
    await cache.write('key1', 'value1', broadcast=False)
    
    # Read
    value = await cache.read('key1')
    assert value == 'value1'

@pytest.mark.asyncio
async def test_cache_miss():
    """Test cache miss"""
    cache = CacheNode(node_id=1, max_size=100, policy='LRU')
    
    value = await cache.read('nonexistent')
    assert value is None

@pytest.mark.asyncio
async def test_cache_eviction_lru():
    """Test LRU eviction policy"""
    cache = CacheNode(node_id=1, max_size=2, policy='LRU')
    
    await cache.write('key1', 'value1', broadcast=False)
    await cache.write('key2', 'value2', broadcast=False)
    await cache.write('key3', 'value3', broadcast=False)
    
    # key1 should be evicted
    value1 = await cache.read('key1')
    assert value1 is None
    
    value2 = await cache.read('key2')
    assert value2 == 'value2'

@pytest.mark.asyncio
async def test_cache_invalidation():
    """Test cache invalidation"""
    cache = CacheNode(node_id=1, max_size=100, policy='LRU')
    
    await cache.write('key1', 'value1', broadcast=False)
    await cache.invalidate('key1')
    
    # Should still exist but be invalid
    assert 'key1' in cache.cache
    assert cache.cache['key1'].state == CacheState.INVALID
