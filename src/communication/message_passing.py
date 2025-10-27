"""Message passing implementation using asyncio"""
import asyncio
import json
from enum import Enum
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
import aiohttp
import logging

logger = logging.getLogger(__name__)

class MessageType(Enum):
    """Message types for distributed communication"""
    # Raft messages
    REQUEST_VOTE = "request_vote"
    REQUEST_VOTE_RESPONSE = "request_vote_response"
    APPEND_ENTRIES = "append_entries"
    APPEND_ENTRIES_RESPONSE = "append_entries_response"
    
    # Lock messages
    ACQUIRE_LOCK = "acquire_lock"
    RELEASE_LOCK = "release_lock"
    LOCK_RESPONSE = "lock_response"
    
    # Queue messages
    ENQUEUE = "enqueue"
    DEQUEUE = "dequeue"
    QUEUE_RESPONSE = "queue_response"
    
    # Cache messages
    CACHE_READ = "cache_read"
    CACHE_WRITE = "cache_write"
    CACHE_INVALIDATE = "cache_invalidate"
    CACHE_RESPONSE = "cache_response"
    
    # Health check
    HEARTBEAT = "heartbeat"
    PING = "ping"
    PONG = "pong"

@dataclass
class Message:
    """Message structure for inter-node communication"""
    type: MessageType
    sender_id: int
    receiver_id: int
    term: int
    data: Dict[str, Any]
    timestamp: float
    
    def to_dict(self) -> Dict:
        """Convert message to dictionary"""
        return {
            'type': self.type.value,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'term': self.term,
            'data': self.data,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Message':
        """Create message from dictionary"""
        return cls(
            type=MessageType(data['type']),
            sender_id=data['sender_id'],
            receiver_id=data['receiver_id'],
            term=data['term'],
            data=data['data'],
            timestamp=data['timestamp']
        )

class MessagePassing:
    """Handle message passing between nodes"""
    
    def __init__(self, node_id: int, host: str, port: int):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.handlers: Dict[MessageType, Callable] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self._server = None
        self._app = None
    
    async def start(self):
        """Start message passing server"""
        from aiohttp import web
        
        self._app = web.Application()
        self._app.router.add_post('/message', self._handle_incoming_message)
        self._app.router.add_get('/health', self._handle_health_check)
        
        runner = web.AppRunner(self._app)
        await runner.setup()
        self._server = web.TCPSite(runner, self.host, self.port)
        await self._server.start()
        
        self.session = aiohttp.ClientSession()
        logger.info(f"Node {self.node_id} message server started on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop message passing server"""
        if self.session:
            await self.session.close()
        if self._server:
            await self._server.stop()
    
    def register_handler(self, message_type: MessageType, handler: Callable):
        """Register message handler"""
        self.handlers[message_type] = handler
    
    async def send_message(self, target_host: str, target_port: int, message: Message) -> Optional[Dict]:
        """Send message to another node"""
        try:
            url = f"http://{target_host}:{target_port}/message"
            async with self.session.post(url, json=message.to_dict(), timeout=5) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Failed to send message: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error sending message to {target_host}:{target_port}: {e}")
            return None
    
    async def broadcast_message(self, nodes: list, message: Message) -> Dict[int, Optional[Dict]]:
        """Broadcast message to multiple nodes"""
        tasks = []
        for node_host, node_port in nodes:
            tasks.append(self.send_message(node_host, node_port, message))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {i: result for i, result in enumerate(results)}
    
    async def _handle_incoming_message(self, request):
        """Handle incoming message"""
        from aiohttp import web
        
        try:
            data = await request.json()
            message = Message.from_dict(data)
            
            if message.type in self.handlers:
                response = await self.handlers[message.type](message)
                return web.json_response(response)
            else:
                logger.warning(f"No handler for message type: {message.type}")
                return web.json_response({'status': 'error', 'message': 'No handler'}, status=400)
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return web.json_response({'status': 'error', 'message': str(e)}, status=500)
    
    async def _handle_health_check(self, request):
        """Handle health check"""
        from aiohttp import web
        return web.json_response({'status': 'healthy', 'node_id': self.node_id})
