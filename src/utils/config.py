"""Configuration management using pydantic-settings"""
from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # Node Configuration
    node_id: int = int(os.getenv('NODE_ID', 1))
    node_host: str = os.getenv('NODE_HOST', 'localhost')
    node_port: int = int(os.getenv('NODE_PORT', 8000))
    
    # Cluster Configuration
    cluster_nodes: str = os.getenv('CLUSTER_NODES', 'localhost:8000')
    min_cluster_size: int = 3
    
    # Redis Configuration
    redis_host: str = 'localhost'
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ''
    
    # Raft Configuration
    election_timeout_min: int = 150  # ms
    election_timeout_max: int = 300  # ms
    heartbeat_interval: int = 50     # ms
    
    # Cache Configuration
    cache_size: int = 1000
    cache_policy: str = 'LRU'
    cache_ttl: int = 3600
    
    # Queue Configuration
    queue_partition_count: int = 256
    queue_replication_factor: int = 3
    
    # Performance Settings
    max_workers: int = 10
    batch_size: int = 100
    
    # Monitoring
    metrics_port: int = 9090
    log_level: str = 'INFO'
    
    def get_cluster_nodes(self) -> List[str]:
        """Parse cluster nodes from comma-separated string"""
        return [node.strip() for node in self.cluster_nodes.split(',')]
    
    class Config:
        env_file = '.env'
        case_sensitive = False

settings = Settings()
