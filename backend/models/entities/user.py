import uuid
import hashlib
import base64
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Session, relationship
from passlib.context import CryptContext

from backend.models.entities.base import Base


# Valid RBAC roles
ROLE_PRIMARY_SOVEREIGN = "primary_sovereign"
ROLE_DEPUTY_SOVEREIGN = "deputy_sovereign"
ROLE_OBSERVER = "observer"
VALID_ROLES = {ROLE_PRIMARY_SOVEREIGN, ROLE_DEPUTY_SOVEREIGN, ROLE_OBSERVER}


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _new_uuid() -> str:
    """Generate a new UUID4 string. Used as the default for User.id."""
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    # String UUID primary key — matches the VARCHAR(36) column created by
    # migration 001. The default= ensures Python always supplies a value so
    # SQLAlchemy never sends NULL in the INSERT.
    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)

    username         = Column(String(50),  unique=True, index=True, nullable=False)
    email            = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password  = Column(String(255), nullable=False)
    is_active        = Column(Boolean, default=False,  nullable=False)
    is_admin         = Column(Boolean, default=False,  nullable=False)
    is_pending       = Column(Boolean, default=True,   nullable=False)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    # D3: Track last successful DB-backed login time.
    # Populated by auth.py on every successful login. NULL for users who
    # have not logged in since migration 007_settings_improvements ran.
    last_login_at    = Column(DateTime(timezone=True), nullable=True)

    # Phase 11.1 — RBAC role system
    role             = Column(String(30), default=ROLE_OBSERVER, nullable=False)
    delegated_by_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    role_expires_at  = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    chat_messages = relationship(
        "ChatMessage",
        back_populates="user",
        order_by="ChatMessage.created_at.desc()",
    )
    conversations = relationship(
        "Conversation",
        back_populates="user",
        order_by="Conversation.updated_at.desc()",
    )

    # Phase 11.1 — Delegation relationships
    # lazy="select" (SQLAlchemy default) issues a single SELECT per relationship
    # access rather than "dynamic" which returns an un-executed query object and
    # causes an N+1 pattern when iterating inside RBACService.get_effective_permissions.
    delegations_granted = relationship(
        "Delegation",
        foreign_keys="Delegation.grantor_id",
        back_populates="grantor",
        lazy="select",
    )
    delegations_received = relationship(
        "Delegation",
        foreign_keys="Delegation.grantee_id",
        back_populates="grantee",
        lazy="select",
    )
    delegated_by = relationship(
        "User",
        remote_side="User.id",
        foreign_keys=[delegated_by_id],
        uselist=False,
    )

    # ------------------------------------------------------------------ #
    #  RBAC helpers                                                        #
    # ------------------------------------------------------------------ #

    @property
    def effective_role(self) -> str:
        """Return the effective role, considering expiry and is_admin compat."""
        # Backward compat: is_admin=True always maps to primary_sovereign
        if self.is_admin:
            return ROLE_PRIMARY_SOVEREIGN
        # Check if role has expired
        if self.role_expires_at and datetime.utcnow() > self.role_expires_at:
            return ROLE_OBSERVER
        return self.role or ROLE_OBSERVER

    @property
    def can_veto(self) -> bool:
        """Whether this user has veto power."""
        return self.effective_role in (ROLE_PRIMARY_SOVEREIGN, ROLE_DEPUTY_SOVEREIGN)

    @property
    def is_sovereign(self) -> bool:
        """Whether this user is the primary sovereign."""
        return self.effective_role == ROLE_PRIMARY_SOVEREIGN

    # ------------------------------------------------------------------ #
    #  Password helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _prehash_password(password: str) -> str:
        """
        Pre-hash with SHA-256 before bcrypt to support passwords > 72 bytes
        without silently truncating entropy.
        """
        sha256_hash = hashlib.sha256(password.encode("utf-8")).digest()
        return base64.b64encode(sha256_hash).decode("ascii")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against its stored bcrypt hash."""
        prehashed = User._prehash_password(plain_password)
        return pwd_context.verify(prehashed, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storage (SHA-256 pre-hash + bcrypt)."""
        prehashed = User._prehash_password(password)
        return pwd_context.hash(prehashed)

    # ------------------------------------------------------------------ #
    #  Class-level DB helpers                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def create_user(
        cls,
        db: Session,
        username: str,
        email: str,
        password: str,
        is_admin: bool = False,
        is_active: bool = False,
        is_pending: bool = True,
        role: str = ROLE_OBSERVER,
    ) -> "User":
        """Create a new user with a hashed password and commit."""
        # Sync role with is_admin for backward compat
        effective_role = ROLE_PRIMARY_SOVEREIGN if is_admin else role
        user = cls(
            username=username,
            email=email,
            hashed_password=cls.hash_password(password),
            is_active=is_active,
            is_admin=is_admin,
            is_pending=is_pending,
            role=effective_role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @classmethod
    def authenticate(cls, db: Session, username: str, password: str) -> "User | None":
        """Return the user if credentials are valid, else None."""
        user = db.query(cls).filter(cls.username == username).first()
        if not user:
            return None
        if not cls.verify_password(password, user.hashed_password):
            return None
        return user

    # ------------------------------------------------------------------ #
    #  Serialisation                                                       #
    # ------------------------------------------------------------------ #

    def to_dict(self, include_sensitive: bool = False) -> dict:
        data = {
            "id":           self.id,
            "username":     self.username,
            "email":        self.email,
            "is_active":    self.is_active,
            "is_admin":     self.is_admin,
            "is_pending":   self.is_pending,
            "role":         self.effective_role,
            "can_veto":     self.can_veto,
            "is_sovereign": self.is_sovereign,
            "role_expires_at": self.role_expires_at.isoformat() if self.role_expires_at else None,
            "delegated_by_id": self.delegated_by_id,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "updated_at":   self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_sensitive:
            data["hashed_password"] = self.hashed_password
        return data

    def __repr__(self) -> str:
        return f"<User {self.username!r} id={self.id}>"