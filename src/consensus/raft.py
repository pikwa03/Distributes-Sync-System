"""Raft Consensus Algorithm Implementation - Enhanced"""
import asyncio
import random
import time
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

from ..communication.message_passing import MessagePassing, Message, MessageType
from ..utils.config import settings

logger = logging.getLogger(__name__)


class RaftState(Enum):
    """Raft node states"""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class LogEntry:
    """Log entry structure"""
    term: int
    index: int
    command: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class RaftNode:
    """Raft consensus node implementation"""
    
    def __init__(self, node_id: int, cluster_nodes: List[tuple]):
        self.node_id = node_id
        self.cluster_nodes = cluster_nodes
        
        # Persistent state
        self.current_term = 0
        self.voted_for: Optional[int] = None
        self.log: List[LogEntry] = []
        
        # Volatile state
        self.commit_index = 0
        self.last_applied = 0
        self.state = RaftState.FOLLOWER
        
        # Leader state
        self.next_index: Dict[int, int] = {}
        self.match_index: Dict[int, int] = {}
        
        # Timing
        self.election_timeout = self._get_election_timeout()
        self.last_heartbeat = time.time()
        self.heartbeat_interval = settings.heartbeat_interval / 1000.0
        
        # Tasks
        self._election_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = True  # <-- ADD THIS
        
        # Message passing
        self.message_passing: Optional[MessagePassing] = None
        
        # Leader info
        self.leader_id: Optional[int] = None
        
        # Election statistics (for debugging/monitoring)
        self.elections_started = 0
        self.elections_won = 0
        
        logger.info(f"🔧 Raft node {self.node_id} initialized")
    
    def _get_election_timeout(self) -> float:
        """Get randomized election timeout"""
        min_timeout = settings.election_timeout_min / 1000.0
        max_timeout = settings.election_timeout_max / 1000.0
        timeout = random.uniform(min_timeout, max_timeout)
        logger.debug(f"Node {self.node_id}: Election timeout set to {timeout:.2f}s")
        return timeout
    
    async def start(self, message_passing: MessagePassing):
        """Start Raft node"""
        self.message_passing = message_passing
        
        # Register message handlers
        self.message_passing.register_handler(MessageType.REQUEST_VOTE, self._handle_request_vote)
        self.message_passing.register_handler(MessageType.REQUEST_VOTE_RESPONSE, self._handle_vote_response)
        self.message_passing.register_handler(MessageType.APPEND_ENTRIES, self._handle_append_entries)
        self.message_passing.register_handler(MessageType.APPEND_ENTRIES_RESPONSE, self._handle_append_entries_response)
        
        # Start election timer
        self._election_task = asyncio.create_task(self._election_timer())
        logger.info(f"✅ Raft node {self.node_id} started as {self.state.value.upper()}")
    
    async def stop(self):
        """Stop Raft node"""
        self._running = False  # <-- ADD THIS
        if self._election_task:
            self._election_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        logger.info(f"🛑 Raft node {self.node_id} stopped")
    
    async def _election_timer(self):
        """Election timeout mechanism"""
        while self._running:  # <-- CHANGE THIS
            try:
                await asyncio.sleep(0.1)
                
                if self.state == RaftState.LEADER:
                    continue
                
                elapsed = time.time() - self.last_heartbeat
                if elapsed > self.election_timeout:
                    logger.warning(f"⏰ Node {self.node_id}: Election timeout ({elapsed:.2f}s > {self.election_timeout:.2f}s)")
                    await self._start_election()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error in election timer: {e}")
    
    async def _start_election(self):
        """Start leader election"""
        self.elections_started += 1  # <-- ADD THIS
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.last_heartbeat = time.time()
        self.election_timeout = self._get_election_timeout()
        
        votes_received = 1
        votes_needed = (len(self.cluster_nodes) + 1) // 2 + 1
        
        logger.info(f"🗳️  Node {self.node_id}: Starting election for term {self.current_term} "
                   f"(need {votes_needed} votes)")
        
        # Request votes from all other nodes
        vote_requests = []
        for host, port in self.cluster_nodes:
            message = Message(
                type=MessageType.REQUEST_VOTE,
                sender_id=self.node_id,
                receiver_id=-1,
                term=self.current_term,
                data={
                    'candidate_id': self.node_id,
                    'last_log_index': len(self.log) - 1 if self.log else -1,
                    'last_log_term': self.log[-1].term if self.log else 0
                },
                timestamp=time.time()
            )
            vote_requests.append(
                self.message_passing.send_message(host, port, message)
            )
        
        # Wait for vote responses (with timeout)
        try:
            responses = await asyncio.wait_for(
                asyncio.gather(*vote_requests, return_exceptions=True),
                timeout=self.election_timeout / 2  # <-- ADD TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Node {self.node_id}: Vote collection timeout")
            responses = []
        
        for response in responses:
            if isinstance(response, dict) and response.get('vote_granted'):
                votes_received += 1
                logger.debug(f"✓ Node {self.node_id}: Received vote ({votes_received}/{votes_needed})")
        
        # Check if won election
        if votes_received >= votes_needed and self.state == RaftState.CANDIDATE:
            self.elections_won += 1  # <-- ADD THIS
            await self._become_leader()
        else:
            logger.info(f"❌ Node {self.node_id}: Election failed "
                       f"({votes_received}/{votes_needed} votes)")
    
    async def _become_leader(self):
        """Become leader"""
        self.state = RaftState.LEADER
        self.leader_id = self.node_id
        
        # Initialize leader state
        last_log_index = len(self.log) - 1 if self.log else -1
        for i, (host, port) in enumerate(self.cluster_nodes):
            self.next_index[i] = last_log_index + 1
            self.match_index[i] = -1
        
        logger.info(f"👑 Node {self.node_id}: BECAME LEADER for term {self.current_term} "
                   f"(elections: {self.elections_won}/{self.elections_started})")
        
        # Start sending heartbeats
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._send_heartbeats())
    
    async def _send_heartbeats(self):
        """Send periodic heartbeats as leader"""
        while self.state == RaftState.LEADER and self._running:  # <-- ADD _running check
            try:
                logger.debug(f"💓 Node {self.node_id}: Sending heartbeats (term {self.current_term})")
                
                tasks = []
                for host, port in self.cluster_nodes:
                    message = Message(
                        type=MessageType.APPEND_ENTRIES,
                        sender_id=self.node_id,
                        receiver_id=-1,
                        term=self.current_term,
                        data={
                            'leader_id': self.node_id,
                            'prev_log_index': len(self.log) - 1 if self.log else -1,
                            'prev_log_term': self.log[-1].term if self.log else 0,
                            'entries': [],
                            'leader_commit': self.commit_index
                        },
                        timestamp=time.time()
                    )
                    tasks.append(self.message_passing.send_message(host, port, message))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Count successful heartbeats
                successful = sum(1 for r in results if not isinstance(r, Exception))
                logger.debug(f"💓 Node {self.node_id}: Heartbeat sent to {successful}/{len(tasks)} nodes")
                
                await asyncio.sleep(self.heartbeat_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Error sending heartbeats: {e}")
    
    async def _handle_request_vote(self, message: Message) -> Dict:
        """Handle RequestVote RPC"""
        vote_granted = False
        
        # Update term if necessary
        if message.term > self.current_term:
            logger.info(f"📈 Node {self.node_id}: Updating term {self.current_term} → {message.term}")
            self.current_term = message.term
            self.voted_for = None
            self.state = RaftState.FOLLOWER
        
        # Check if can grant vote
        last_log_index = len(self.log) - 1 if self.log else -1
        last_log_term = self.log[-1].term if self.log else 0
        
        log_ok = (message.data['last_log_term'] > last_log_term or
                  (message.data['last_log_term'] == last_log_term and
                   message.data['last_log_index'] >= last_log_index))
        
        if (message.term >= self.current_term and
            (self.voted_for is None or self.voted_for == message.data['candidate_id']) and
            log_ok):
            vote_granted = True
            self.voted_for = message.data['candidate_id']
            self.last_heartbeat = time.time()
            logger.info(f"✓ Node {self.node_id}: GRANTED vote to {message.data['candidate_id']} "
                       f"for term {message.term}")
        else:
            logger.info(f"✗ Node {self.node_id}: DENIED vote to {message.data['candidate_id']} "
                       f"for term {message.term} (already voted: {self.voted_for})")
        
        return {
            'term': self.current_term,
            'vote_granted': vote_granted
        }
    
    async def _handle_vote_response(self, message: Message) -> Dict:
        """Handle RequestVote response"""
        return {'status': 'ok'}
    
    async def _handle_append_entries(self, message: Message) -> Dict:
        """Handle AppendEntries RPC"""
        success = False
        
        # Update term if necessary
        if message.term > self.current_term:
            logger.info(f"📈 Node {self.node_id}: Updating term {self.current_term} → {message.term}")
            self.current_term = message.term
            self.state = RaftState.FOLLOWER
            self.voted_for = None
        
        # Reset election timer (received heartbeat)
        self.last_heartbeat = time.time()
        
        # Update leader
        if message.term >= self.current_term:
            if self.leader_id != message.data['leader_id']:
                logger.info(f"👑 Node {self.node_id}: New leader identified: {message.data['leader_id']}")
            self.leader_id = message.data['leader_id']
            if self.state != RaftState.FOLLOWER:
                logger.info(f"↓ Node {self.node_id}: Stepping down to FOLLOWER")
                self.state = RaftState.FOLLOWER
            success = True
        
        return {
            'term': self.current_term,
            'success': success
        }
    
    async def _handle_append_entries_response(self, message: Message) -> Dict:
        """Handle AppendEntries response"""
        return {'status': 'ok'}
    
    async def append_entry(self, command: Dict[str, Any]) -> bool:
        """Append entry to log (only leader can do this)"""
        if self.state != RaftState.LEADER:
            logger.warning(f"❌ Node {self.node_id}: Cannot append entry (not leader)")
            return False
        
        entry = LogEntry(
            term=self.current_term,
            index=len(self.log),
            command=command
        )
        self.log.append(entry)
        
        logger.info(f"📝 Leader {self.node_id}: Appended entry {entry.index} "
                   f"(term {entry.term})")
        return True
    
    def is_leader(self) -> bool:
        """Check if this node is the leader"""
        return self.state == RaftState.LEADER
    
    def get_leader_id(self) -> Optional[int]:
        """Get current leader ID"""
        return self.leader_id
    
    def get_status(self) -> Dict:  # <-- ADD THIS
        """Get current Raft status (for monitoring/debugging)"""
        return {
            'node_id': self.node_id,
            'state': self.state.value,
            'term': self.current_term,
            'leader_id': self.leader_id,
            'log_length': len(self.log),
            'commit_index': self.commit_index,
            'elections_started': self.elections_started,
            'elections_won': self.elections_won,
            'voted_for': self.voted_for
        }
