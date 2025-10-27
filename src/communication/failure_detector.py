"""Failure detector using heartbeat mechanism"""
import asyncio
import time
from typing import Dict, Set, Callable
import logging

logger = logging.getLogger(__name__)

class FailureDetector:
    """Detect node failures using heartbeat"""
    
    def __init__(self, timeout: float = 5.0, check_interval: float = 1.0):
        self.timeout = timeout
        self.check_interval = check_interval
        self.last_heartbeat: Dict[int, float] = {}
        self.suspected_nodes: Set[int] = set()
        self.failed_nodes: Set[int] = set()
        self.failure_callbacks: list[Callable] = []
        self.recovery_callbacks: list[Callable] = []
        self._running = False
        self._task = None
    
    def register_failure_callback(self, callback: Callable):
        """Register callback for node failure"""
        self.failure_callbacks.append(callback)
    
    def register_recovery_callback(self, callback: Callable):
        """Register callback for node recovery"""
        self.recovery_callbacks.append(callback)
    
    def record_heartbeat(self, node_id: int):
        """Record heartbeat from node"""
        current_time = time.time()
        self.last_heartbeat[node_id] = current_time
        
        # Check if node recovered
        if node_id in self.failed_nodes:
            self.failed_nodes.remove(node_id)
            self.suspected_nodes.discard(node_id)
            logger.info(f"Node {node_id} recovered")
            for callback in self.recovery_callbacks:
                asyncio.create_task(callback(node_id))
    
    async def start(self):
        """Start failure detection"""
        self._running = True
        self._task = asyncio.create_task(self._check_failures())
        logger.info("Failure detector started")
    
    async def stop(self):
        """Stop failure detection"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _check_failures(self):
        """Periodically check for failures"""
        while self._running:
            try:
                current_time = time.time()
                
                for node_id, last_time in list(self.last_heartbeat.items()):
                    elapsed = current_time - last_time
                    
                    if elapsed > self.timeout:
                        if node_id not in self.failed_nodes:
                            self.suspected_nodes.add(node_id)
                            
                            if elapsed > self.timeout * 2:
                                self.failed_nodes.add(node_id)
                                logger.warning(f"Node {node_id} failed (no heartbeat for {elapsed:.2f}s)")
                                
                                for callback in self.failure_callbacks:
                                    await callback(node_id)
                
                await asyncio.sleep(self.check_interval)
            
            except Exception as e:
                logger.error(f"Error in failure detection: {e}")
    
    def is_alive(self, node_id: int) -> bool:
        """Check if node is alive"""
        return node_id not in self.failed_nodes
    
    def get_failed_nodes(self) -> Set[int]:
        """Get set of failed nodes"""
        return self.failed_nodes.copy()
    
    def get_alive_nodes(self) -> Set[int]:
        """Get set of alive nodes"""
        return set(self.last_heartbeat.keys()) - self.failed_nodes
