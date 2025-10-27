"""Unit tests for Lock Manager"""
import pytest
import asyncio
from src.nodes.lock_manager import LockManager, LockType
from src.consensus.raft import RaftNode, RaftState

@pytest.mark.asyncio
async def test_acquire_exclusive_lock():
    """Test acquiring exclusive lock"""
    raft = RaftNode(node_id=1, cluster_nodes=[])
    raft.state = RaftState.LEADER
    
    lock_manager = LockManager(node_id=1, raft=raft)
    
    result = await lock_manager.acquire_lock('resource1', client_id=100, lock_type=LockType.EXCLUSIVE)
    assert result is True
    assert 'resource1' in lock_manager.locks

@pytest.mark.asyncio
async def test_shared_locks():
    """Test multiple shared locks"""
    raft = RaftNode(node_id=1, cluster_nodes=[])
    raft.state = RaftState.LEADER
    
    lock_manager = LockManager(node_id=1, raft=raft)
    
    # First shared lock
    result1 = await lock_manager.acquire_lock('resource1', client_id=100, lock_type=LockType.SHARED)
    assert result1 is True
    
    # Second shared lock on same resource
    result2 = await lock_manager.acquire_lock('resource1', client_id=101, lock_type=LockType.SHARED)
    assert result2 is True
    
    assert len(lock_manager.locks['resource1'].holders) == 2

@pytest.mark.asyncio
async def test_exclusive_lock_blocks():
    """Test exclusive lock blocks other locks"""
    raft = RaftNode(node_id=1, cluster_nodes=[])
    raft.state = RaftState.LEADER
    
    lock_manager = LockManager(node_id=1, raft=raft)
    
    # Acquire exclusive lock
    result1 = await lock_manager.acquire_lock('resource1', client_id=100, lock_type=LockType.EXCLUSIVE)
    assert result1 is True
    
    # Try to acquire another lock (should timeout)
    result2 = await lock_manager.acquire_lock('resource1', client_id=101, lock_type=LockType.EXCLUSIVE, timeout=0.5)
    assert result2 is False

@pytest.mark.asyncio
async def test_release_lock():
    """Test releasing lock"""
    raft = RaftNode(node_id=1, cluster_nodes=[])
    raft.state = RaftState.LEADER
    
    lock_manager = LockManager(node_id=1, raft=raft)
    
    await lock_manager.acquire_lock('resource1', client_id=100, lock_type=LockType.EXCLUSIVE)
    result = await lock_manager.release_lock('resource1', client_id=100)
    
    assert result is True
    assert 'resource1' not in lock_manager.locks
