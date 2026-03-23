#!/usr/bin/env python3
"""Verify the admin user was created."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.base import SessionLocal
from app.models.user import User
from app.models.workspace import Workspace

db = SessionLocal()
try:
    user = db.query(User).filter(User.email == "admin@yopmail.com").first()
    if user:
        print("✅ User found in database:")
        print(f"   ID: {user.id}")
        print(f"   Email: {user.email}")
        print(f"   Full Name: {user.full_name}")
        print(f"   Is Active: {user.is_active}")
        print(f"   Is Superuser: {user.is_superuser}")
        
        workspace = db.query(Workspace).filter(Workspace.owner_id == user.id).first()
        if workspace:
            print(f"   Workspace: {workspace.name} (ID: {workspace.id})")
    else:
        print("❌ User not found!")
finally:
    db.close()

