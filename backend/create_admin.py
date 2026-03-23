#!/usr/bin/env python3
"""
Script to create an admin user.
Usage: python create_admin.py
"""
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash
from app.models.workspace import Workspace

def create_admin_user():
    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == "admin@yopmail.com").first()
        if existing_user:
            print("❌ User with email admin@yopmail.com already exists!")
            return
        
        # Create admin user
        hashed_password = get_password_hash("Admin@123")
        admin_user = User(
            email="admin@yopmail.com",
            hashed_password=hashed_password,
            full_name="admin",
            is_active=True,
            is_superuser=True
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        # Create a default workspace for the admin
        default_workspace = Workspace(
            name="Default Workspace",
            owner_id=admin_user.id
        )
        db.add(default_workspace)
        db.commit()
        
        print("✅ Admin user created successfully!")
        print(f"   Email: admin@yopmail.com")
        print(f"   Full Name: admin")
        print(f"   Password: Admin@123")
        print(f"   User ID: {admin_user.id}")
        print(f"   Workspace ID: {default_workspace.id}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating admin user: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == '__main__':
    create_admin_user()

