"""
End-to-End Encryption for Inter-Node Communication
Implements AES-256 encryption with key exchange
"""

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import base64
import json
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class EncryptionManager:
    """Manages encryption for secure inter-node communication"""
    
    def __init__(self):
        # Generate RSA key pair for key exchange
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()
        
        # Symmetric key for data encryption (AES-256)
        self.symmetric_key = Fernet.generate_key()
        self.cipher = Fernet(self.symmetric_key)
        
        logger.info("Encryption manager initialized with RSA-2048 + AES-256")
    
    def get_public_key_pem(self) -> bytes:
        """Export public key in PEM format for sharing"""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
    
    def encrypt_symmetric_key(self, peer_public_key_pem: bytes) -> bytes:
        """Encrypt symmetric key with peer's public key (for key exchange)"""
        peer_public_key = serialization.load_pem_public_key(
            peer_public_key_pem,
            backend=default_backend()
        )
        
        encrypted_key = peer_public_key.encrypt(
            self.symmetric_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return encrypted_key
    
    def decrypt_symmetric_key(self, encrypted_key: bytes) -> bytes:
        """Decrypt symmetric key with own private key"""
        symmetric_key = self.private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return symmetric_key
    
    def encrypt_message(self, message: Dict) -> str:
        """Encrypt message for secure transmission"""
        try:
            # Convert to JSON
            json_data = json.dumps(message).encode()
            
            # Encrypt with symmetric key
            encrypted = self.cipher.encrypt(json_data)
            
            # Base64 encode for transmission
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def decrypt_message(self, encrypted_message: str) -> Dict:
        """Decrypt received message"""
        try:
            # Base64 decode
            encrypted = base64.b64decode(encrypted_message.encode('utf-8'))
            
            # Decrypt with symmetric key
            decrypted = self.cipher.decrypt(encrypted)
            
            # Parse JSON
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise
    
    def sign_message(self, message: Dict) -> bytes:
        """Sign message for authenticity verification"""
        json_data = json.dumps(message).encode()
        
        signature = self.private_key.sign(
            json_data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return signature
    
    def verify_signature(self, message: Dict, signature: bytes, peer_public_key_pem: bytes) -> bool:
        """Verify message signature"""
        try:
            peer_public_key = serialization.load_pem_public_key(
                peer_public_key_pem,
                backend=default_backend()
            )
            
            json_data = json.dumps(message).encode()
            
            peer_public_key.verify(
                signature,
                json_data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False


class SecureChannel:
    """Manages secure communication channel between nodes"""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.encryption_manager = EncryptionManager()
        self.peer_keys: Dict[str, bytes] = {}  # peer_id -> public_key
        
        logger.info(f"Secure channel initialized for node {node_id}")
    
    def register_peer(self, peer_id: str, public_key_pem: bytes):
        """Register peer's public key"""
        self.peer_keys[peer_id] = public_key_pem
        logger.info(f"Registered peer {peer_id} for secure communication")
    
    def send_secure_message(self, peer_id: str, message: Dict) -> Tuple[str, bytes]:
        """Encrypt and sign message for peer"""
        if peer_id not in self.peer_keys:
            raise ValueError(f"Peer {peer_id} not registered")
        
        # Encrypt message
        encrypted = self.encryption_manager.encrypt_message(message)
        
        # Sign message
        signature = self.encryption_manager.sign_message(message)
        
        return encrypted, signature
    
    def receive_secure_message(self, peer_id: str, encrypted_message: str, signature: bytes) -> Dict:
        """Decrypt and verify message from peer"""
        if peer_id not in self.peer_keys:
            raise ValueError(f"Peer {peer_id} not registered")
        
        # Decrypt message
        message = self.encryption_manager.decrypt_message(encrypted_message)
        
        # Verify signature
        if not self.encryption_manager.verify_signature(message, signature, self.peer_keys[peer_id]):
            raise ValueError("Invalid signature - message tampered!")
        
        return message
