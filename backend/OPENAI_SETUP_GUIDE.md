# OpenAI API Key Setup Guide

## Quick Steps

1. **Get API Key**
   - Go to: https://platform.openai.com/api-keys
   - Click "+ Create new secret key"
   - Name it: "Sync Software Check Extraction"
   - **Copy the key immediately** (shown only once)
   - Format: `sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

2. **Set Up Billing**
   - Go to: https://platform.openai.com/account/billing
   - Add payment method (credit card)
   - Set spending limits:
     - Soft limit: $20/month
     - Hard limit: $50/month

3. **Add to .env File**
   ```bash
   # In backend/.env file, add:
   OPENAI_API_KEY=sk-proj-your-actual-key-here
   ```

4. **Test the Key**
   ```bash
   cd backend
   source venv/bin/activate
   python3 -c "from openai import OpenAI; import os; client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')); print('✅ API Key is valid!')"
   ```

## Important Notes

- ⚠️ **Never commit your API key to Git**
- ✅ The key is already in `.gitignore`
- 💰 New accounts get $5-10 free credits
- 📊 Cost: ~$0.01-0.03 per check extraction
- 🔒 Set spending limits to avoid unexpected charges

## Direct Links

- API Keys: https://platform.openai.com/api-keys
- Billing: https://platform.openai.com/account/billing
- Usage: https://platform.openai.com/usage
- Pricing: https://platform.openai.com/pricing

