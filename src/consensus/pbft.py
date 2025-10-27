"""PBFT (Practical Byzantine Fault Tolerance) Implementation - BONUS"""
import asyncio
import time
from enum import Enum
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

class PBFTPhase(Enum):
    """PBFT consensus phases"""
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    REPLY = "reply"

@dataclass
class PBFTMessage:
    """PBFT message structure"""
    phase: PBFTPhase
    view: int
    sequence: int
    digest: str
    node_id: int
    timestamp: float

class PBFTNode:
    """PBFT node implementation"""
    
    def __init__(self, node_id: int, total_nodes: int):
        self.node_id = node_id
        self.total_nodes = total_nodes
        self.f = (total_nodes - 1) // 3  # Maximum faulty nodes
        
        # State
        self.view = 0
        self.sequence = 0
        self.primary_id = 0
        
        # Message logs
        self.pre_prepare_log: Dict[int, PBFTMessage] = {}
        self.prepare_log: Dict[int, List[PBFTMessage]] = {}
        self.commit_log: Dict[int, List[PBFTMessage]] = {}
        
        # Executed requests
        self.executed: Set[int] = set()
        
        logger.info(f"PBFT Node {node_id} initialized (f={self.f})")
    
    def is_primary(self) -> bool:
        """Check if this node is primary"""
        return self.node_id == (self.view % self.total_nodes)
    
    async def request(self, operation: str) -> bool:
        """Client request (only primary receives)"""
        if not self.is_primary():
            return False
        
        self.sequence += 1
        digest = self._compute_digest(operation)
        
        # Broadcast PRE-PREPARE
        pre_prepare_msg = PBFTMessage(
            phase=PBFTPhase.PRE_PREPARE,
            view=self.view,
            sequence=self.sequence,
            digest=digest,
            node_id=self.node_id,
            timestamp=time.time()
        )
        
        self.pre_prepare_log[self.sequence] = pre_prepare_msg
        logger.info(f"Primary {self.node_id}: PRE-PREPARE seq={self.sequence}")
        
        return True
    
    async def handle_pre_prepare(self, msg: PBFTMessage) -> bool:
        """Handle PRE-PREPARE message"""
        # Validate message
        if msg.view != self.view:
            return False
        
        if msg.node_id != (self.view % self.total_nodes):
            return False  # Not from primary
        
        self.pre_prepare_log[msg.sequence] = msg
        
        # Send PREPARE to all nodes
        prepare_msg = PBFTMessage(
            phase=PBFTPhase.PREPARE,
            view=self.view,
            sequence=msg.sequence,
            digest=msg.digest,
            node_id=self.node_id,
            timestamp=time.time()
        )
        
        if msg.sequence not in self.prepare_log:
            self.prepare_log[msg.sequence] = []
        self.prepare_log[msg.sequence].append(prepare_msg)
        
        logger.info(f"Node {self.node_id}: PREPARE seq={msg.sequence}")
        return True
    
    async def handle_prepare(self, msg: PBFTMessage) -> bool:
        """Handle PREPARE message"""
        if msg.view != self.view:
            return False
        
        if msg.sequence not in self.prepare_log:
            self.prepare_log[msg.sequence] = []
        
        self.prepare_log[msg.sequence].append(msg)
        
        # Check if received 2f PREPARE messages
        if len(self.prepare_log[msg.sequence]) >= 2 * self.f:
            # Send COMMIT
            commit_msg = PBFTMessage(
                phase=PBFTPhase.COMMIT,
                view=self.view,
                sequence=msg.sequence,
                digest=msg.digest,
                node_id=self.node_id,
                timestamp=time.time()
            )
            
            if msg.sequence not in self.commit_log:
                self.commit_log[msg.sequence] = []
            self.commit_log[msg.sequence].append(commit_msg)
            
            logger.info(f"Node {self.node_id}: COMMIT seq={msg.sequence}")
        
        return True
    
    async def handle_commit(self, msg: PBFTMessage) -> bool:
        """Handle COMMIT message"""
        if msg.view != self.view:
            return False
        
        if msg.sequence not in self.commit_log:
            self.commit_log[msg.sequence] = []
        
        self.commit_log[msg.sequence].append(msg)
        
        # Check if received 2f+1 COMMIT messages
        if len(self.commit_log[msg.sequence]) >= 2 * self.f + 1:
            if msg.sequence not in self.executed:
                # Execute operation
                await self._execute_operation(msg.sequence, msg.digest)
                self.executed.add(msg.sequence)
                logger.info(f"Node {self.node_id}: EXECUTED seq={msg.sequence}")
                return True
        
        return False
    
    async def _execute_operation(self, sequence: int, digest: str):
        """Execute the operation"""
        # Placeholder for actual operation execution
        logger.info(f"Node {self.node_id}: Executing operation seq={sequence}, digest={digest}")
    
    def _compute_digest(self, data: str) -> str:
        """Compute message digest"""
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    async def view_change(self):
        """Initiate view change"""
        self.view += 1
        self.primary_id = self.view % self.total_nodes
        logger.info(f"Node {self.node_id}: View change to view={self.view}, primary={self.primary_id}")
