from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from backend.models.database import Base
from sqlalchemy.orm import relationship 
import hashlib
import base64

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    is_pending = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    chat_messages = relationship("ChatMessage", back_populates="user", order_by="ChatMessage.created_at.desc()")
    conversations = relationship("Conversation", back_populates="user", order_by="Conversation.updated_at.desc()")
    
    @staticmethod
    def _prehash_password(password: str) -> str:
        """
        Pre-hash password with SHA256 to handle passwords longer than 72 bytes.
        This preserves full password entropy while ensuring bcrypt compatibility.
        """
        # SHA256 produces a fixed 32-byte hash regardless of input length
        sha256_hash = hashlib.sha256(password.encode('utf-8')).digest()
        # Convert to base64 to get a string (44 chars) that bcrypt can handle
        return base64.b64encode(sha256_hash).decode('ascii')
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        # Apply same pre-hashing as during storage
        prehashed = User._prehash_password(plain_password)
        return pwd_context.verify(prehashed, hashed_password)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storage using SHA256 pre-hash + bcrypt."""
        # Pre-hash to handle long passwords while preserving entropy
        prehashed = User._prehash_password(password)
        return pwd_context.hash(prehashed)
    
    @classmethod
    def create_user(cls, db: Session, username: str, email: str, password: str) -> 'User':
        """Create a new user with hashed password."""
        hashed = cls.hash_password(password)
        user = cls(
            username=username,
            email=email,
            hashed_password=hashed,
            is_active=False,
            is_pending=True,
            is_admin=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    @classmethod
    def authenticate(cls, db: Session, username: str, password: str) -> 'User | None':
        """Authenticate a user with username and password."""
        user = db.query(cls).filter(cls.username == username).first()
        if not user:
            return None
        if not cls.verify_password(password, user.hashed_password):
            return None
        return user
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert user to dictionary."""
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "is_pending": self.is_pending,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_sensitive:
            data["hashed_password"] = self.hashed_password
        return data