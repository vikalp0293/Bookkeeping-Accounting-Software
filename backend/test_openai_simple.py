#!/usr/bin/env python3
"""
Simple test script for OpenAI API key.
Fixed version of your test code.
"""
from openai import OpenAI
import os
from app.core.config import settings

# Get API key from settings
api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")

if not api_key:
    print("❌ ERROR: OPENAI_API_KEY not found")
    print("Add it to .env file: OPENAI_API_KEY=sk-proj-...")
    exit(1)

print("🔍 Testing OpenAI API Key...")
print(f"Key: {api_key[:15]}...{api_key[-10:]}")
print()

# Initialize client
client = OpenAI(api_key=api_key)

# Fixed test code - using correct API format
try:
    print("📤 Sending test request...")
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # Fixed: gpt-5-nano doesn't exist
        messages=[  # Fixed: use 'messages' not 'input'
            {"role": "user", "content": "write a haiku about ai"}
        ],
        max_tokens=50
    )
    
    # Fixed: correct way to get response
    output_text = response.choices[0].message.content
    print("✅ API Key is valid!")
    print(f"\n📝 Response:\n{output_text}")
    print("\n🎉 Your OpenAI API key works!")
    
except Exception as e:
    error_msg = str(e)
    print(f"❌ Error: {error_msg}")
    
    if "insufficient_quota" in error_msg or "billing" in error_msg.lower():
        print("\n💡 Billing is not enabled yet.")
        print("   To use the API, you need to:")
        print("   1. Go to: https://platform.openai.com/account/billing")
        print("   2. Add payment method")
        print("   3. Set spending limits")
    elif "Invalid API key" in error_msg or "Incorrect API key" in error_msg:
        print("\n💡 API key is invalid or incorrect")
    else:
        print(f"\n💡 Full error: {error_msg}")

