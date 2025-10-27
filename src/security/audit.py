"""
Tamper-Proof Audit Logging
Implements blockchain-like audit trail with cryptographic verification
"""

import hashlib
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

@dataclass
class AuditEntry:
    """Single audit log entry"""
    timestamp: str
    event_type: str
    user_id: str
    action: str
    resource: str
    result: str
    details: Dict
    previous_hash: str
    hash: str

class TamperProofAuditLog:
    """Blockchain-style tamper-proof audit logging"""
    
    def __init__(self):
        self.chain: List[AuditEntry] = []
        self.genesis_hash = self._calculate_hash("GENESIS_BLOCK")
        
        # Create genesis entry
        genesis = AuditEntry(
            timestamp=datetime.now().isoformat(),
            event_type="SYSTEM",
            user_id="system",
            action="INIT",
            resource="audit_log",
            result="SUCCESS",
            details={"message": "Audit log initialized"},
            previous_hash="0",
            hash=self.genesis_hash
        )
        self.chain.append(genesis)
        
        logger.info("Tamper-proof audit log initialized")
    
    def _calculate_hash(self, data: str) -> str:
        """Calculate SHA-256 hash"""
        return hashlib.sha256(data.encode()).hexdigest()
    
    def log_event(
        self,
        event_type: str,
        user_id: str,
        action: str,
        resource: str,
        result: str,
        details: Dict = None
    ) -> AuditEntry:
        """Log new audit event"""
        
        # Get previous hash
        previous_hash = self.chain[-1].hash if self.chain else "0"
        
        # Create entry without hash first
        entry_data = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "result": result,
            "details": details or {},
            "previous_hash": previous_hash
        }
        
        # Calculate hash of entry
        entry_json = json.dumps(entry_data, sort_keys=True)
        entry_hash = self._calculate_hash(entry_json)
        
        # Create final entry with hash
        entry = AuditEntry(**entry_data, hash=entry_hash)
        
        # Add to chain
        self.chain.append(entry)
        
        logger.info(f"Audit logged: {event_type} - {action} by {user_id} on {resource}: {result}")
        
        return entry
    
    def verify_integrity(self) -> bool:
        """Verify entire audit chain integrity"""
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i-1]
            
            # Check if previous_hash matches
            if current.previous_hash != previous.hash:
                logger.error(f"Audit chain broken at entry {i}: previous_hash mismatch")
                return False
            
            # Recalculate hash and verify
            entry_data = {
                "timestamp": current.timestamp,
                "event_type": current.event_type,
                "user_id": current.user_id,
                "action": current.action,
                "resource": current.resource,
                "result": current.result,
                "details": current.details,
                "previous_hash": current.previous_hash
            }
            entry_json = json.dumps(entry_data, sort_keys=True)
            calculated_hash = self._calculate_hash(entry_json)
            
            if calculated_hash != current.hash:
                logger.error(f"Audit chain broken at entry {i}: hash mismatch (tampered)")
                return False
        
        logger.info("Audit chain integrity verified - no tampering detected")
        return True
    
    def get_user_activity(self, user_id: str) -> List[AuditEntry]:
        """Get all activity for specific user"""
        return [entry for entry in self.chain if entry.user_id == user_id]
    
    def get_resource_access(self, resource: str) -> List[AuditEntry]:
        """Get all access to specific resource"""
        return [entry for entry in self.chain if entry.resource == resource]
    
    def export_audit_trail(self) -> List[Dict]:
        """Export full audit trail"""
        return [asdict(entry) for entry in self.chain]
