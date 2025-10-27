"""Distributed Queue with Consistent Hashing"""
import asyncio
import hashlib
import pickle
import time
from typing import Dict, List, Optional, Any
from collections import deque
import logging

from ..communication.message_passing import MessagePassing, Message, MessageType
from ..utils.metrics import metrics

logger = logging.getLogger(__name__)

class ConsistentHashRing:
    """Consistent hashing ring implementation"""
    
    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: Dict[int, int] = {}  # hash -> node_id
        self.sorted_keys: List[int] = []
        self.nodes: set = set()
    
    def add_node(self, node_id: int):
        """Add node to the ring"""
        if node_id in self.nodes:
            return
        
        self.nodes.add(node_id)
        
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_value = self._hash(virtual_key)
            self.ring[hash_value] = node_id
        
        self.sorted_keys = sorted(self.ring.keys())
        logger.info(f"Added node {node_id} to hash ring")
    
    def remove_node(self, node_id: int):
        """Remove node from the ring"""
        if node_id not in self.nodes:
            return
        
        self.nodes.remove(node_id)
        
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_value = self._hash(virtual_key)
            if hash_value in self.ring:
                del self.ring[hash_value]
        
        self.sorted_keys = sorted(self.ring.keys())
        logger.info(f"Removed node {node_id} from hash ring")
    
    def get_node(self, key: str) -> Optional[int]:
        """Get node responsible for key"""
        if not self.ring:
            return None
        
        hash_value = self._hash(key)
        
        # Binary search for the first node >= hash_value
        idx = self._binary_search(hash_value)
        
        if idx >= len(self.sorted_keys):
            idx = 0
        
        return self.ring[self.sorted_keys[idx]]
    
    def _hash(self, key: str) -> int:
        """Hash function"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def _binary_search(self, value: int) -> int:
        """Binary search in sorted keys"""
        left, right = 0, len(self.sorted_keys)
        
        while left < right:
            mid = (left + right) // 2
            if self.sorted_keys[mid] < value:
                left = mid + 1
            else:
                right = mid
        
        return left

class QueueNode:
    """Distributed queue node with consistent hashing"""
    
    def __init__(self, node_id: int, partition_count: int = 256):
        self.node_id = node_id
        self.partition_count = partition_count
        self.hash_ring = ConsistentHashRing()
        
        # Local queue storage
        self.queues: Dict[str, deque] = {}
        self.queue_metadata: Dict[str, Dict] = {}
        
        # Message persistence
        self.persistent_storage: Dict[str, List[Any]] = {}
        
        self.message_passing: Optional[MessagePassing] = None
    
    async def start(self, message_passing: MessagePassing):
        """Start queue node"""
        self.message_passing = message_passing
        
        # Register handlers
        self.message_passing.register_handler(MessageType.ENQUEUE, self._handle_enqueue)
        self.message_passing.register_handler(MessageType.DEQUEUE, self._handle_dequeue)
        
        # Add self to hash ring
        self.hash_ring.add_node(self.node_id)
        
        logger.info(f"Queue Node {self.node_id} started")
    
    async def stop(self):
        """Stop queue node"""
        # Persist all queues before shutdown
        await self._persist_all_queues()
        logger.info(f"Queue Node {self.node_id} stopped")
    
    async def enqueue(self, queue_name: str, item: Any, priority: int = 0) -> bool:
        """Enqueue an item"""
        start_time = time.time()
        
        # Determine responsible node
        responsible_node = self.hash_ring.get_node(queue_name)
        
        if responsible_node != self.node_id:
            # Forward to responsible node
            logger.debug(f"Forwarding enqueue to node {responsible_node}")
            return False
        
        # Create queue if not exists
        if queue_name not in self.queues:
            self.queues[queue_name] = deque()
            self.queue_metadata[queue_name] = {
                'created_at': time.time(),
                'total_enqueued': 0,
                'total_dequeued': 0
            }
        
        # Add item to queue
        self.queues[queue_name].append({
            'item': item,
            'priority': priority,
            'timestamp': time.time(),
            'attempts': 0
        })
        
        self.queue_metadata[queue_name]['total_enqueued'] += 1
        
        # Persist to storage
        await self._persist_queue(queue_name)
        
        metrics.record_request('enqueue', 'success')
        latency = time.time() - start_time
        metrics.record_latency('enqueue', latency)
        
        logger.info(f"Enqueued item to queue '{queue_name}'")
        return True
    
    async def dequeue(self, queue_name: str, timeout: float = 0) -> Optional[Any]:
        """Dequeue an item"""
        start_time = time.time()
        
        # Determine responsible node
        responsible_node = self.hash_ring.get_node(queue_name)
        
        if responsible_node != self.node_id:
            logger.debug(f"Forwarding dequeue to node {responsible_node}")
            return None
        
        if queue_name not in self.queues or not self.queues[queue_name]:
            if timeout > 0:
                # Wait for item
                end_time = start_time + timeout
                while time.time() < end_time:
                    await asyncio.sleep(0.1)
                    if queue_name in self.queues and self.queues[queue_name]:
                        break
                else:
                    metrics.record_request('dequeue', 'timeout')
                    return None
            else:
                metrics.record_request('dequeue', 'empty')
                return None
        
        # Get item from queue
        item_data = self.queues[queue_name].popleft()
        item = item_data['item']
        
        self.queue_metadata[queue_name]['total_dequeued'] += 1
        
        # Persist changes
        await self._persist_queue(queue_name)
        
        metrics.record_request('dequeue', 'success')
        latency = time.time() - start_time
        metrics.record_latency('dequeue', latency)
        
        logger.info(f"Dequeued item from queue '{queue_name}'")
        return item
    
    async def _persist_queue(self, queue_name: str):
        """Persist queue to storage for recovery"""
        if queue_name not in self.queues:
            return
        
        # Convert deque to list for serialization
        queue_data = list(self.queues[queue_name])
        self.persistent_storage[queue_name] = queue_data
        
        # In production, write to disk or Redis
        # For now, keep in memory
    
    async def _persist_all_queues(self):
        """Persist all queues"""
        for queue_name in self.queues.keys():
            await self._persist_queue(queue_name)
    
    async def recover_queue(self, queue_name: str) -> bool:
        """Recover queue from persistent storage"""
        if queue_name not in self.persistent_storage:
            return False
        
        self.queues[queue_name] = deque(self.persistent_storage[queue_name])
        logger.info(f"Recovered queue '{queue_name}' from storage")
        return True
    
    async def _handle_enqueue(self, message: Message) -> Dict:
        """Handle enqueue request"""
        queue_name = message.data['queue_name']
        item = message.data['item']
        priority = message.data.get('priority', 0)
        
        success = await self.enqueue(queue_name, item, priority)
        
        return {
            'success': success,
            'queue_name': queue_name
        }
    
    async def _handle_dequeue(self, message: Message) -> Dict:
        """Handle dequeue request"""
        queue_name = message.data['queue_name']
        timeout = message.data.get('timeout', 0)
        
        item = await self.dequeue(queue_name, timeout)
        
        return {
            'success': item is not None,
            'item': item,
            'queue_name': queue_name
        }
    
    def get_queue_stats(self, queue_name: str) -> Optional[Dict]:
        """Get queue statistics"""
        if queue_name not in self.queue_metadata:
            return None
        
        return {
            'name': queue_name,
            'size': len(self.queues.get(queue_name, [])),
            'metadata': self.queue_metadata[queue_name]
        }
