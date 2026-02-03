from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from backend.models.database import Base

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)  # Changed: Users need approval
    is_admin = Column(Boolean, default=False)
    is_pending = Column(Boolean, default=True)  # New: For approval workflow
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storage."""
        return pwd_context.hash(password)
    
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