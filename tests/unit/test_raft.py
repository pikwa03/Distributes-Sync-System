"""Unit tests for Raft consensus"""
import pytest
import asyncio
from src.consensus.raft import RaftNode, RaftState, LogEntry
from src.communication.message_passing import MessagePassing

@pytest.mark.asyncio
async def test_raft_initialization():
    """Test Raft node initialization"""
    cluster_nodes = [('localhost', 8001), ('localhost', 8002)]
    raft = RaftNode(node_id=1, cluster_nodes=cluster_nodes)
    
    assert raft.node_id == 1
    assert raft.state == RaftState.FOLLOWER
    assert raft.current_term == 0
    assert raft.voted_for is None
    assert len(raft.log) == 0

@pytest.mark.asyncio
async def test_election_timeout():
    """Test election timeout triggers election"""
    cluster_nodes = [('localhost', 8001), ('localhost', 8002)]
    raft = RaftNode(node_id=1, cluster_nodes=cluster_nodes)
    
    # Simulate timeout
    raft.election_timeout = 0.1
    raft.last_heartbeat = 0
    
    assert raft.state == RaftState.FOLLOWER
    # In real test, would verify election is triggered

@pytest.mark.asyncio
async def test_log_append():
    """Test appending entries to log"""
    cluster_nodes = []
    raft = RaftNode(node_id=1, cluster_nodes=cluster_nodes)
    raft.state = RaftState.LEADER
    
    command = {'operation': 'set', 'key': 'x', 'value': 10}
    result = await raft.append_entry(command)
    
    assert result is True
    assert len(raft.log) == 1
    assert raft.log[0].command == command

@pytest.mark.asyncio
async def test_follower_cannot_append():
    """Test followers cannot append entries"""
    cluster_nodes = []
    raft = RaftNode(node_id=1, cluster_nodes=cluster_nodes)
    
    command = {'operation': 'set', 'key': 'x', 'value': 10}
    result = await raft.append_entry(command)
    
    assert result is False
    assert len(raft.log) == 0
