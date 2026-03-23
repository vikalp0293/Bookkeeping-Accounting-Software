#!/usr/bin/env python3
"""
Test script to verify OpenAI API key is configured correctly.
Run this after adding your API key to .env file.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings

def test_openai_key():
    """Test if OpenAI API key is configured and valid."""
    print("🔍 Testing OpenAI API Key Configuration...")
    print("=" * 60)
    
    # Check if key is set
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not found in .env file")
        print("\n📝 To fix:")
        print("1. Open backend/.env file")
        print("2. Add: OPENAI_API_KEY=sk-proj-your-key-here")
        print("3. Save and run this script again")
        return False
    
    # Check key format
    if not api_key.startswith("sk-"):
        print("⚠️  WARNING: API key format looks incorrect")
        print(f"   Expected format: sk-proj-...")
        print(f"   Your key starts with: {api_key[:5]}...")
        return False
    
    print(f"✅ API Key found: {api_key[:10]}...{api_key[-4:]}")
    
    # Try to import OpenAI
    try:
        from openai import OpenAI
        print("✅ OpenAI library installed")
    except ImportError:
        print("❌ ERROR: OpenAI library not installed")
        print("\n📝 To fix:")
        print("   pip install openai>=1.0.0")
        return False
    
    # Test API connection
    print("\n🔌 Testing API connection...")
    try:
        client = OpenAI(api_key=api_key)
        
        # Make a simple test call (cheap, ~$0.0001)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "Say 'API key is working' if you can read this."}
            ],
            max_tokens=10
        )
        
        result = response.choices[0].message.content
        print(f"✅ API connection successful!")
        print(f"   Response: {result}")
        print("\n🎉 Your OpenAI API key is configured correctly!")
        print("\n💡 Next steps:")
        print("   - You can now use GPT-4 Vision for check extraction")
        print("   - Check your usage at: https://platform.openai.com/usage")
        return True
        
    except Exception as e:
        error_msg = str(e)
        if "Incorrect API key" in error_msg or "Invalid API key" in error_msg:
            print("❌ ERROR: Invalid API key")
            print("   Please check your API key in .env file")
        elif "insufficient_quota" in error_msg or "billing" in error_msg.lower():
            print("❌ ERROR: Billing not set up or insufficient credits")
            print("   Go to: https://platform.openai.com/account/billing")
            print("   Add payment method and check credits")
        else:
            print(f"❌ ERROR: {error_msg}")
        return False

if __name__ == "__main__":
    success = test_openai_key()
    sys.exit(0 if success else 1)

