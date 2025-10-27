"""Load testing scenarios using Locust"""
from locust import HttpUser, task, between, events
import json
import random
import time

class DistributedSystemUser(HttpUser):
    """Simulated user for load testing"""
    wait_time = between(1, 3)
    
    def on_start(self):
        """Initialize on user start"""
        self.client_id = random.randint(1000, 9999)
    
    @task(3)
    def cache_operations(self):
        """Test cache operations"""
        key = f"key_{random.randint(1, 100)}"
        
        # Write to cache
        self.client.post("/cache/write", json={
            'key': key,
            'value': f'value_{time.time()}'
        })
        
        # Read from cache
        self.client.get(f"/cache/read?key={key}")
    
    @task(2)
    def queue_operations(self):
        """Test queue operations"""
        queue_name = f"queue_{random.randint(1, 10)}"
        
        # Enqueue
        self.client.post("/queue/enqueue", json={
            'queue_name': queue_name,
            'item': {'data': f'item_{time.time()}'}
        })
        
        # Dequeue
        self.client.post("/queue/dequeue", json={
            'queue_name': queue_name
        })
    
    @task(1)
    def lock_operations(self):
        """Test lock operations"""
        resource_id = f"resource_{random.randint(1, 20)}"
        
        # Acquire lock
        response = self.client.post("/lock/acquire", json={
            'resource_id': resource_id,
            'client_id': self.client_id,
            'lock_type': 'exclusive'
        })
        
        if response.status_code == 200:
            # Simulate work
            time.sleep(0.1)
            
            # Release lock
            self.client.post("/lock/release", json={
                'resource_id': resource_id,
                'client_id': self.client_id
            })

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """On test start"""
    print("Load test starting...")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """On test stop"""
    print("Load test completed!")
    print(f"Total requests: {environment.stats.total.num_requests}")
    print(f"Total failures: {environment.stats.total.num_failures}")
    print(f"Average response time: {environment.stats.total.avg_response_time:.2f}ms")

# Run with: locust -f benchmarks/load_test_scenarios.py --host=http://localhost:8000
