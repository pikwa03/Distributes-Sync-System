"""Distributed Lock Manager with deadlock detection"""
import asyncio
import time
from typing import Dict, Set, Optional
from enum import Enum
import logging

from ..communication.message_passing import MessagePassing, Message, MessageType
from ..consensus.raft import RaftNode
from ..utils.metrics import metrics

logger = logging.getLogger(__name__)

class LockType(Enum):
    """Lock types"""
    SHARED = "shared"
    EXCLUSIVE = "exclusive"

class Lock:
    """Lock representation"""
    def __init__(self, resource_id: str, lock_type: LockType, holder_id: int):
        self.resource_id = resource_id
        self.lock_type = lock_type
        self.holders: Set[int] = {holder_id}
        self.waiters: list = []
        self.timestamp = time.time()

class LockManager:
    """Distributed lock manager using Raft consensus"""
    
    def __init__(self, node_id: int, raft: RaftNode):
        self.node_id = node_id
        self.raft = raft
        self.locks: Dict[str, Lock] = {}
        self.held_locks: Dict[int, Set[str]] = {}  # client_id -> set of resource_ids
        self.wait_for_graph: Dict[int, Set[int]] = {}  # For deadlock detection
        self.message_passing: Optional[MessagePassing] = None
        self._deadlock_task: Optional[asyncio.Task] = None
    
    async def start(self, message_passing: MessagePassing):
        """Start lock manager"""
        self.message_passing = message_passing
        
        # Register handlers
        self.message_passing.register_handler(MessageType.ACQUIRE_LOCK, self._handle_acquire_lock)
        self.message_passing.register_handler(MessageType.RELEASE_LOCK, self._handle_release_lock)
        
        # Start deadlock detection
        self._deadlock_task = asyncio.create_task(self._detect_deadlocks())
        logger.info(f"Lock Manager started on node {self.node_id}")
    
    async def stop(self):
        """Stop lock manager"""
        if self._deadlock_task:
            self._deadlock_task.cancel()
    
    async def acquire_lock(self, resource_id: str, client_id: int, 
                          lock_type: LockType = LockType.EXCLUSIVE, 
                          timeout: float = 10.0) -> bool:
        """Acquire a lock"""
        start_time = time.time()
        
        # Only leader can grant locks
        if not self.raft.is_leader():
            logger.warning(f"Node {self.node_id} is not leader, cannot acquire lock")
            return False
        
        while time.time() - start_time < timeout:
            if await self._try_acquire_lock(resource_id, client_id, lock_type):
                metrics.record_request('acquire_lock', 'success')
                latency = time.time() - start_time
                metrics.record_latency('acquire_lock', latency)
                return True
            
            await asyncio.sleep(0.1)
        
        metrics.record_request('acquire_lock', 'timeout')
        logger.warning(f"Lock acquisition timeout for resource {resource_id} by client {client_id}")
        return False
    
    async def _try_acquire_lock(self, resource_id: str, client_id: int, lock_type: LockType) -> bool:
        """Try to acquire lock"""
        if resource_id not in self.locks:
            # No lock exists, create new one
            self.locks[resource_id] = Lock(resource_id, lock_type, client_id)
            
            if client_id not in self.held_locks:
                self.held_locks[client_id] = set()
            self.held_locks[client_id].add(resource_id)
            
            logger.info(f"Lock acquired: resource={resource_id}, client={client_id}, type={lock_type.value}")
            return True
        
        lock = self.locks[resource_id]
        
        # Check if can acquire
        if lock_type == LockType.SHARED and lock.lock_type == LockType.SHARED:
            # Multiple shared locks allowed
            lock.holders.add(client_id)
            
            if client_id not in self.held_locks:
                self.held_locks[client_id] = set()
            self.held_locks[client_id].add(resource_id)
            
            logger.info(f"Shared lock acquired: resource={resource_id}, client={client_id}")
            return True
        
        # Cannot acquire, add to waiters
        if client_id not in lock.waiters:
            lock.waiters.append(client_id)
            self._update_wait_for_graph(client_id, lock.holders)
        
        return False
    
    async def release_lock(self, resource_id: str, client_id: int) -> bool:
        """Release a lock"""
        start_time = time.time()
        
        if not self.raft.is_leader():
            return False
        
        if resource_id not in self.locks:
            logger.warning(f"Cannot release non-existent lock: {resource_id}")
            return False
        
        lock = self.locks[resource_id]
        
        if client_id not in lock.holders:
            logger.warning(f"Client {client_id} does not hold lock {resource_id}")
            return False
        
        # Remove holder
        lock.holders.remove(client_id)
        
        if client_id in self.held_locks:
            self.held_locks[client_id].discard(resource_id)
        
        # Remove from wait-for graph
        if client_id in self.wait_for_graph:
            del self.wait_for_graph[client_id]
        
        # If no more holders, grant to waiters
        if not lock.holders:
            if lock.waiters:
                next_client = lock.waiters.pop(0)
                lock.holders.add(next_client)
                
                if next_client not in self.held_locks:
                    self.held_locks[next_client] = set()
                self.held_locks[next_client].add(resource_id)
                
                logger.info(f"Lock granted to waiting client: resource={resource_id}, client={next_client}")
            else:
                # No waiters, remove lock
                del self.locks[resource_id]
        
        metrics.record_request('release_lock', 'success')
        latency = time.time() - start_time
        metrics.record_latency('release_lock', latency)
        
        logger.info(f"Lock released: resource={resource_id}, client={client_id}")
        return True
    
    def _update_wait_for_graph(self, waiter: int, holders: Set[int]):
        """Update wait-for graph for deadlock detection"""
        if waiter not in self.wait_for_graph:
            self.wait_for_graph[waiter] = set()
        self.wait_for_graph[waiter].update(holders)
    
    async def _detect_deadlocks(self):
        """Detect deadlocks using cycle detection in wait-for graph"""
        while True:
            try:
                await asyncio.sleep(1.0)
                
                # Find cycles using DFS
                visited = set()
                rec_stack = set()
                
                def has_cycle(node: int) -> bool:
                    visited.add(node)
                    rec_stack.add(node)
                    
                    if node in self.wait_for_graph:
                        for neighbor in self.wait_for_graph[node]:
                            if neighbor not in visited:
                                if has_cycle(neighbor):
                                    return True
                            elif neighbor in rec_stack:
                                return True
                    
                    rec_stack.remove(node)
                    return False
                
                for node in list(self.wait_for_graph.keys()):
                    if node not in visited:
                        if has_cycle(node):
                            logger.warning(f"Deadlock detected involving client {node}")
                            await self._resolve_deadlock(node)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in deadlock detection: {e}")
    
    async def _resolve_deadlock(self, client_id: int):
        """Resolve deadlock by aborting youngest transaction"""
        if client_id in self.held_locks:
            for resource_id in list(self.held_locks[client_id]):
                await self.release_lock(resource_id, client_id)
            logger.info(f"Resolved deadlock by releasing locks from client {client_id}")
    
    async def _handle_acquire_lock(self, message: Message) -> Dict:
        """Handle acquire lock request"""
        resource_id = message.data['resource_id']
        client_id = message.data['client_id']
        lock_type = LockType(message.data.get('lock_type', 'exclusive'))
        
        success = await self.acquire_lock(resource_id, client_id, lock_type)
        
        return {
            'success': success,
            'resource_id': resource_id
        }
    
    async def _handle_release_lock(self, message: Message) -> Dict:
        """Handle release lock request"""
        resource_id = message.data['resource_id']
        client_id = message.data['client_id']
        
        success = await self.release_lock(resource_id, client_id)
        
        return {
            'success': success,
            'resource_id': resource_id
        }
