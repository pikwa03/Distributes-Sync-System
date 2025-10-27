"""
Role-Based Access Control (RBAC)
Implements fine-grained permission management
"""

from enum import Enum
from typing import Dict, List, Set, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

class Role(Enum):
    """System roles"""
    ADMIN = "admin"
    OPERATOR = "operator"
    READER = "reader"
    GUEST = "guest"

class Permission(Enum):
    """System permissions"""
    # Lock permissions
    LOCK_ACQUIRE = "lock:acquire"
    LOCK_RELEASE = "lock:release"
    LOCK_VIEW = "lock:view"
    
    # Queue permissions
    QUEUE_ENQUEUE = "queue:enqueue"
    QUEUE_DEQUEUE = "queue:dequeue"
    QUEUE_VIEW = "queue:view"
    
    # Cache permissions
    CACHE_WRITE = "cache:write"
    CACHE_READ = "cache:read"
    CACHE_DELETE = "cache:delete"
    
    # Admin permissions
    NODE_MANAGE = "node:manage"
    SYSTEM_CONFIG = "system:config"
    USER_MANAGE = "user:manage"

@dataclass
class User:
    """User with role and metadata"""
    user_id: str
    username: str
    role: Role
    metadata: Dict = None

class RBACManager:
    """Manages role-based access control"""
    
    def __init__(self):
        # Define role-permission mapping
        self.role_permissions: Dict[Role, Set[Permission]] = {
            Role.ADMIN: {
                # Full access to everything
                Permission.LOCK_ACQUIRE, Permission.LOCK_RELEASE, Permission.LOCK_VIEW,
                Permission.QUEUE_ENQUEUE, Permission.QUEUE_DEQUEUE, Permission.QUEUE_VIEW,
                Permission.CACHE_WRITE, Permission.CACHE_READ, Permission.CACHE_DELETE,
                Permission.NODE_MANAGE, Permission.SYSTEM_CONFIG, Permission.USER_MANAGE
            },
            Role.OPERATOR: {
                # Can operate but not configure
                Permission.LOCK_ACQUIRE, Permission.LOCK_RELEASE, Permission.LOCK_VIEW,
                Permission.QUEUE_ENQUEUE, Permission.QUEUE_DEQUEUE, Permission.QUEUE_VIEW,
                Permission.CACHE_WRITE, Permission.CACHE_READ,
            },
            Role.READER: {
                # Read-only access
                Permission.LOCK_VIEW,
                Permission.QUEUE_VIEW,
                Permission.CACHE_READ,
            },
            Role.GUEST: {
                # Minimal access
                Permission.CACHE_READ,
            }
        }
        
        # User registry
        self.users: Dict[str, User] = {}
        
        logger.info("RBAC manager initialized")
    
    def register_user(self, user_id: str, username: str, role: Role):
        """Register new user with role"""
        user = User(user_id=user_id, username=username, role=role)
        self.users[user_id] = user
        logger.info(f"Registered user {username} ({user_id}) with role {role.value}")
        return user
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return self.users.get(user_id)
    
    def has_permission(self, user_id: str, permission: Permission) -> bool:
        """Check if user has specific permission"""
        user = self.users.get(user_id)
        if not user:
            logger.warning(f"Unknown user {user_id} attempting access")
            return False
        
        has_perm = permission in self.role_permissions[user.role]
        
        if not has_perm:
            logger.warning(f"User {user.username} ({user.role.value}) denied permission {permission.value}")
        
        return has_perm
    
    def check_permission(self, user_id: str, permission: Permission):
        """Check permission and raise exception if denied"""
        if not self.has_permission(user_id, permission):
            user = self.users.get(user_id)
            role = user.role.value if user else "unknown"
            raise PermissionError(
                f"User {user_id} (role: {role}) does not have permission {permission.value}"
            )
    
    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """Get all permissions for user"""
        user = self.users.get(user_id)
        if not user:
            return set()
        return self.role_permissions[user.role]
    
    def change_user_role(self, user_id: str, new_role: Role, admin_id: str):
        """Change user's role (admin only)"""
        # Check admin permission
        self.check_permission(admin_id, Permission.USER_MANAGE)
        
        user = self.users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        old_role = user.role
        user.role = new_role
        
        logger.info(f"User {user.username} role changed from {old_role.value} to {new_role.value} by admin {admin_id}")

