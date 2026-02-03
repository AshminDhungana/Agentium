#!/usr/bin/env python3
"""
Create the initial admin user.
Run this script after setting up the database.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.database import SessionLocal
from backend.models.entities.user import User

def create_initial_admin():
    db = SessionLocal()
    
    try:
        # Check if admin already exists
        admin = db.query(User).filter(User.username == "admin").first()
        
        if admin:
            print("⚠️  Admin user already exists")
            print(f"   Username: {admin.username}")
            print(f"   Email: {admin.email}")
            print(f"   Active: {admin.is_active}")
            print(f"   Admin: {admin.is_admin}")
            
            response = input("\nDo you want to reset the admin password? (y/n): ")
            if response.lower() == 'y':
                new_password = input("Enter new admin password: ")
                admin.hashed_password = User.hash_password(new_password)
                admin.is_active = True
                admin.is_admin = True
                admin.is_pending = False
                db.commit()
                print("✅ Admin password updated successfully!")
            return
        
        # Create new admin
        print("Creating initial admin user...")
        username = input("Enter admin username [admin]: ") or "admin"
        email = input("Enter admin email [admin@agentium.local]: ") or "admin@agentium.local"
        password = input("Enter admin password: ")
        
        if not password:
            print("❌ Password cannot be empty")
            return
        
        admin = User.create_user(
            db=db,
            username=username,
            email=email,
            password=password
        )
        
        # Make admin active and admin
        admin.is_active = True
        admin.is_admin = True
        admin.is_pending = False
        db.commit()
        
        print(f"\n✅ Admin user created successfully!")
        print(f"   Username: {admin.username}")
        print(f"   Email: {admin.email}")
        print(f"   ID: {admin.id}")
        
    except Exception as e:
        print(f"❌ Error creating admin: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_initial_admin()