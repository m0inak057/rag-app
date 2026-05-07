# Gemini API Setup Guide with Cost Controls

## 🎯 Overview

This guide explains how to safely use Google Gemini API with your RAG application while maintaining strict cost controls and preventing API key abuse.

---

## 📋 Prerequisites

1. **Google Cloud Account** with billing enabled
2. **Gemini API Access** enabled ([Get API Key](https://aistudio.google.com/app/apikeys))
3. Your API key stored in `.env` file

---

## 🔐 Security: Protecting Your API Key

### What We've Done to Protect You

1. **Environment Variables**: API key is NEVER hardcoded—stored in `.env` (which is `.gitignore`'d)
2. **Rate Limiting**: Requests are capped at 60/minute and 100/day by default
3. **Cost Tracking**: Every API call logs token usage and estimated cost
4. **Monthly Budget Cap**: Set a spending limit to prevent surprises

### How to Prevent Key Leakage

```bash
# ❌ NEVER do this:
GEMINI_API_KEY=sk_live_... (hardcoded in code)
git push  # Oops! Key is now public

# ✅ DO this instead:
# 1. Store in .env
# 2. Add .env to .gitignore (already done)
# 3. Never commit .env
```

---

## 💰 Gemini Pricing

**Gemini 1.5 Flash** (recommended for your use case):
- **Input**: $0.075 per 1M tokens
- **Output**: $0.30 per 1M tokens

**Example costs:**
- Typical document chunk: 200-500 tokens
- Typical Q&A response: 100-300 tokens
- **Cost per query**: ~$0.00005 - $0.0002 (less than a penny!)

---

## ⚙️ Configuration

### 1. Get Your Gemini API Key

```bash
# Visit: https://aistudio.google.com/app/apikeys
# Create new API key
# Copy it
```

### 2. Update `.env` File

```env
# .env
GEMINI_API_KEY=your_api_key_here

# Cost Control Settings
GEMINI_RPM=60                    # Max 60 requests/minute
GEMINI_DAILY_LIMIT=100           # Max 100 requests/day
GEMINI_MONTHLY_BUDGET=5.0        # Max $5/month
```

### 3. (Optional) Rate Limiting Adjustment

Adjust these based on your needs:

```env
# For development/testing:
GEMINI_RPM=10
GEMINI_DAILY_LIMIT=50

# For production (heavy use):
GEMINI_RPM=100
GEMINI_DAILY_LIMIT=1000
```

---

## 🛡️ Cost Control Features

### 1. Per-Minute Rate Limiting
```python
# Max 60 requests per minute
# If exceeded → HTTP 429 (Too Many Requests)
```

### 2. Daily Request Limits
```python
# Max 100 requests per day (configurable)
# Resets at midnight UTC
```

### 3. Cost Tracking
Every API call logs:
- Input tokens consumed
- Output tokens generated
- Estimated cost (USD)

**View daily costs via:**
```bash
GET /api/usage-stats/
```

### 4. Token Limits per Request
```python
# Max output tokens capped at 8,000
# Prevents runaway responses
# Safety_settings block harmful content
```

---

## 📊 Monitoring Usage

### Check Usage Stats

```bash
curl -X GET http://localhost:8000/api/usage-stats/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "usage": {
    "daily_cost": {
      "total_cost": 0.0023,
      "input_tokens": 4580,
      "output_tokens": 1245,
      "requests": 15
    },
    "remaining_requests_today": 85,
    "max_daily_requests": 100
  }
}
```

### Check Logs

```bash
# Gemini API calls are logged with:
tail -f your_app.log | grep "Gemini API Usage"

# Output:
# Gemini API Usage - Model: gemini-1.5-flash, 
# Input: 542, Output: 187, Cost: $0.000058
```

---

## 🚨 What Happens at Limits?

### Rate Limit Exceeded (60/min)
```json
{
  "error": "Rate limit exceeded. Please try again later.",
  "usage": { /* current stats */ }
}
```
**Status Code**: HTTP 429

### Daily Limit Exceeded (100/day)
```json
{
  "error": "Rate limit exceeded. Please try again later."
}
```
**Status Code**: HTTP 429

---

## 🔍 Model Selection

### Available Models

```python
'gemini-1.5-flash'  # ✅ Recommended (fastest, cheapest)
'gemini-1.5-pro'    # For complex reasoning tasks
```

### Why Flash?

| Aspect | Flash | Pro |
|--------|-------|-----|
| Cost | 💰 Cheap | 💸💸 Expensive |
| Speed | ⚡ Fast | 🚀 Very Fast |
| Quality | ✅ Good | ✨ Excellent |
| Use Case | Q&A, RAG | Complex reasoning |

---

## 📱 API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/documents/` | GET | List your documents |
| `/api/documents/upload/` | POST | Upload PDF (async) |
| `/api/chat/` | POST | Query document (streaming) |
| `/api/conversations/` | GET | List conversations |
| `/api/usage-stats/` | GET | **Check Gemini usage & costs** |

---

## ⚠️ Important Notes

1. **Never hardcode API keys** in source code
2. **Always use .env** for sensitive data
3. **Monitor `/api/usage-stats/`** regularly
4. **Set realistic rate limits** for your use case
5. **Test with small daily limits** first
6. **Enable billing alerts** in Google Cloud Console

---

## 🆘 Troubleshooting

### "GEMINI_API_KEY not found"

```bash
# Check .env exists
ls -la .env

# Ensure it has: GEMINI_API_KEY=your_key
cat .env | grep GEMINI

# Restart Django
python manage.py runserver
```

### "Rate limit exceeded"

```bash
# Check current usage
curl -X GET http://localhost:8000/api/usage-stats/

# Increase limits in .env
GEMINI_RPM=100
GEMINI_DAILY_LIMIT=200

# Restart Django
```

### "Model not found" Error

Ensure your GEMINI_MODEL in settings.py is supported:
- ✅ `gemini-1.5-flash`
- ✅ `gemini-1.5-pro`

---

## 📈 Best Practices

1. **Start Conservative**: Use low rate limits initially
2. **Monitor Daily**: Check `/api/usage-stats/` each day
3. **Set Budget Alerts**: Google Cloud will notify you
4. **Optimize Prompts**: Shorter prompts = fewer tokens = lower cost
5. **Cache Results**: Store answers to avoid re-querying
6. **Use Flash Model**: 4x cheaper than Pro, sufficient for RAG

---

## 💡 Cost Optimization Tips

```python
# ❌ Expensive
"Summarize this 10,000-word document..."

# ✅ Cheap
"Extract 3 key facts from this document..."

# ❌ Expensive  
response = llm.generate(prompt, max_tokens=512)

# ✅ Cheap
response = llm.generate(prompt, max_tokens=128)
```

---

## 🎓 Example: Monthly Budget Planning

**Assumption**: 1,000 queries/month

```
Avg input tokens: 500
Avg output tokens: 150

Cost calculation:
- Input cost: (500 * 1000) / 1M * $0.075 = $0.04
- Output cost: (150 * 1000) / 1M * $0.30 = $0.05
- Total/month: $0.09 (less than 10 cents!)
```

**Set budget accordingly:**
```env
GEMINI_MONTHLY_BUDGET=1.0  # $1 = 11 months of usage
```

---

## 🔗 Useful Links

- [Get Gemini API Key](https://aistudio.google.com/app/apikeys)
- [Gemini Pricing](https://ai.google.dev/pricing)
- [Google Cloud Console](https://console.cloud.google.com)
- [Gemini API Docs](https://ai.google.dev/docs)

---

**Last Updated**: March 28, 2026  
**Gemini Model Used**: gemini-1.5-flash  
**Cost Control**: ✅ Enabled & Monitored
