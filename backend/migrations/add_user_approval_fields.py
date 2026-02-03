"""
Database migration to add user approval fields.
Run this after updating the User model.
"""

from sqlalchemy import Column, Boolean
from backend.models.database import Base, engine

def upgrade():
    """Add is_pending column to users table."""
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'is_pending'
        """)
        
        if not result.fetchone():
            # Add the column
            conn.execute("""
                ALTER TABLE users 
                ADD COLUMN is_pending BOOLEAN DEFAULT TRUE;
            """)
            print("✅ Added is_pending column to users table")
        else:
            print("⚠️  is_pending column already exists")
        
        # Ensure is_active default is False for new registrations
        conn.execute("""
            ALTER TABLE users 
            ALTER COLUMN is_active SET DEFAULT FALSE;
        """)
        print("✅ Set is_active default to FALSE")

def downgrade():
    """Remove is_pending column."""
    with engine.connect() as conn:
        conn.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_pending;")
        print("✅ Removed is_pending column")

if __name__ == "__main__":
    upgrade()