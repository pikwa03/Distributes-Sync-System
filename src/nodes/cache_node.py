"""Distributed Cache with MESI Protocol"""
import asyncio
import time
from typing import Dict, Optional, Any
from enum import Enum
from collections import OrderedDict
import logging

from ..communication.message_passing import MessagePassing, Message, MessageType
from ..utils.metrics import metrics

logger = logging.getLogger(__name__)

class CacheState(Enum):
    """MESI cache states"""
    MODIFIED = "modified"    # Dirty, exclusive
    EXCLUSIVE = "exclusive"  # Clean, exclusive
    SHARED = "shared"        # Clean, shared
    INVALID = "invalid"      # Invalid

class CacheEntry:
    """Cache entry with MESI state"""
    def __init__(self, key: str, value: Any, state: CacheState = CacheState.EXCLUSIVE):
        self.key = key
        self.value = value
        self.state = state
        self.timestamp = time.time()
        self.access_count = 0
        self.last_access = time.time()

class CacheNode:
    """Distributed cache node with MESI protocol"""
    
    def __init__(self, node_id: int, max_size: int = 1000, policy: str = 'LRU'):
        self.node_id = node_id
        self.max_size = max_size
        self.policy = policy.upper()
        
        # Cache storage
        if self.policy == 'LRU':
            self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        else:
            self.cache: Dict[str, CacheEntry] = {}
        
        # Track other nodes' cache states
        self.remote_cache_states: Dict[int, Dict[str, CacheState]] = {}
        
        self.message_passing: Optional[MessagePassing] = None
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'invalidations': 0
        }
    
    async def start(self, message_passing: MessagePassing):
        """Start cache node"""
        self.message_passing = message_passing
        
        # Register handlers
        self.message_passing.register_handler(MessageType.CACHE_READ, self._handle_cache_read)
        self.message_passing.register_handler(MessageType.CACHE_WRITE, self._handle_cache_write)
        self.message_passing.register_handler(MessageType.CACHE_INVALIDATE, self._handle_cache_invalidate)
        
        logger.info(f"Cache Node {self.node_id} started (policy={self.policy}, size={self.max_size})")
    
    async def stop(self):
        """Stop cache node"""
        logger.info(f"Cache Node {self.node_id} stopped - Stats: {self._stats}")
    
    async def read(self, key: str) -> Optional[Any]:
        """Read from cache"""
        start_time = time.time()
        
        if key in self.cache:
            entry = self.cache[key]
            
            # Check if valid
            if entry.state != CacheState.INVALID:
                entry.access_count += 1
                entry.last_access = time.time()
                
                if self.policy == 'LRU':
                    # Move to end (most recently used)
                    self.cache.move_to_end(key)
                
                self._stats['hits'] += 1
                metrics.record_cache_hit()
                
                latency = time.time() - start_time
                metrics.record_latency('cache_read', latency)
                
                logger.debug(f"Cache hit: key={key}, state={entry.state.value}")
                return entry.value
        
        self._stats['misses'] += 1
        metrics.record_cache_miss()
        
        latency = time.time() - start_time
        metrics.record_latency('cache_read', latency)
        
        logger.debug(f"Cache miss: key={key}")
        return None
    
    async def write(self, key: str, value: Any, broadcast: bool = True) -> bool:
        """Write to cache"""
        start_time = time.time()
        
        # Check if need to evict
        if key not in self.cache and len(self.cache) >= self.max_size:
            await self._evict()
        
        # Invalidate other caches if broadcasting
        if broadcast:
            await self._broadcast_invalidate(key)
        
        # Update local cache
        if key in self.cache:
            entry = self.cache[key]
            entry.value = value
            entry.state = CacheState.MODIFIED
            entry.last_access = time.time()
            entry.access_count += 1
        else:
            entry = CacheEntry(key, value, CacheState.MODIFIED)
            self.cache[key] = entry
        
        if self.policy == 'LRU':
            self.cache.move_to_end(key)
        
        latency = time.time() - start_time
        metrics.record_latency('cache_write', latency)
        
        logger.debug(f"Cache write: key={key}, state={entry.state.value}")
        return True
    
    async def invalidate(self, key: str):
        """Invalidate cache entry"""
        if key in self.cache:
            self.cache[key].state = CacheState.INVALID
            self._stats['invalidations'] += 1
            logger.debug(f"Cache invalidated: key={key}")
    
    async def _evict(self):
        """Evict entry based on policy"""
        if not self.cache:
            return
        
        if self.policy == 'LRU':
            # Remove least recently used (first item)
            key, entry = self.cache.popitem(last=False)
        elif self.policy == 'LFU':
            # Remove least frequently used
            key = min(self.cache.keys(), key=lambda k: self.cache[k].access_count)
            entry = self.cache.pop(key)
        else:
            # Default to FIFO
            key = next(iter(self.cache))
            entry = self.cache.pop(key)
        
        self._stats['evictions'] += 1
        logger.debug(f"Cache evicted: key={key}, policy={self.policy}")
    
    async def _broadcast_invalidate(self, key: str):
        """Broadcast invalidation to other nodes"""
        if not self.message_passing:
            return
        
        # In a real implementation, broadcast to all other cache nodes
        # For now, just log
        logger.debug(f"Broadcasting invalidation for key={key}")
    
    async def _handle_cache_read(self, message: Message) -> Dict:
        """Handle cache read request"""
        key = message.data['key']
        value = await self.read(key)
        
        return {
            'success': value is not None,
            'key': key,
            'value': value
        }
    
    async def _handle_cache_write(self, message: Message) -> Dict:
        """Handle cache write request"""
        key = message.data['key']
        value = message.data['value']
        
        success = await self.write(key, value)
        
        return {
            'success': success,
            'key': key
        }
    
    async def _handle_cache_invalidate(self, message: Message) -> Dict:
        """Handle cache invalidate request"""
        key = message.data['key']
        await self.invalidate(key)
        
        return {
            'success': True,
            'key': key
        }
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total_requests = self._stats['hits'] + self._stats['misses']
        hit_rate = self._stats['hits'] / total_requests if total_requests > 0 else 0
        
        return {
            'node_id': self.node_id,
            'size': len(self.cache),
            'max_size': self.max_size,
            'policy': self.policy,
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'hit_rate': hit_rate,
            'evictions': self._stats['evictions'],
            'invalidations': self._stats['invalidations']
        }
