"""
Certificate Management for Node Authentication
Implements X.509 certificate-based authentication
"""

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class CertificateAuthority:
    """Internal Certificate Authority for node authentication"""
    
    def __init__(self, ca_name: str = "Distributed System CA"):
        # Generate CA private key
        self.ca_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Generate CA certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "ID"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Kalimantan"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Balikpapan"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ITK"),
            x509.NameAttribute(NameOID.COMMON_NAME, ca_name),
        ])
        
        self.ca_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            self.ca_private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True,
        ).sign(self.ca_private_key, hashes.SHA256(), default_backend())
        
        logger.info(f"Certificate Authority initialized: {ca_name}")
    
    def issue_node_certificate(
        self,
        node_id: str,
        node_name: str,
        validity_days: int = 365
    ) -> tuple:
        """Issue certificate for node"""
        
        # Generate node private key
        node_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Create certificate
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "ID"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Kalimantan"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Distributed System"),
            x509.NameAttribute(NameOID.COMMON_NAME, node_name),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, node_id),
        ])
        
        node_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            self.ca_cert.subject
        ).public_key(
            node_private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        ).sign(self.ca_private_key, hashes.SHA256(), default_backend())
        
        logger.info(f"Certificate issued for node {node_id} ({node_name})")
        
        return node_cert, node_private_key
    
    def verify_certificate(self, cert: x509.Certificate) -> bool:
        """Verify certificate was issued by this CA"""
        try:
            # Verify signature
            self.ca_private_key.public_key().verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                padding=None,
                algorithm=cert.signature_hash_algorithm
            )
            
            # Check validity period
            now = datetime.utcnow()
            if now < cert.not_valid_before or now > cert.not_valid_after:
                logger.warning(f"Certificate expired or not yet valid")
                return False
            
            logger.info("Certificate verified successfully")
            return True
        except Exception as e:
            logger.error(f"Certificate verification failed: {e}")
            return False

class NodeAuthenticator:
    """Manages node authentication using certificates"""
    
    def __init__(self, node_id: str, ca: CertificateAuthority):
        self.node_id = node_id
        self.ca = ca
        
        # Get certificate for this node
        self.cert, self.private_key = ca.issue_node_certificate(
            node_id=node_id,
            node_name=f"Node-{node_id}"
        )
        
        # Registry of authenticated peers
        self.authenticated_peers: Dict[str, x509.Certificate] = {}
        
        logger.info(f"Node authenticator initialized for node {node_id}")
    
    def authenticate_peer(self, peer_id: str, peer_cert: x509.Certificate) -> bool:
        """Authenticate peer node by verifying certificate"""
        
        # Verify certificate with CA
        if not self.ca.verify_certificate(peer_cert):
            logger.warning(f"Peer {peer_id} authentication failed: invalid certificate")
            return False
        
        # Register authenticated peer
        self.authenticated_peers[peer_id] = peer_cert
        logger.info(f"Peer {peer_id} authenticated successfully")
        
        return True
    
    def is_peer_authenticated(self, peer_id: str) -> bool:
        """Check if peer is authenticated"""
        return peer_id in self.authenticated_peers
    
    def get_certificate_pem(self) -> bytes:
        """Export certificate in PEM format"""
        return self.cert.public_bytes(serialization.Encoding.PEM)
