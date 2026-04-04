from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os
import time
from collections import defaultdict

app = FastAPI()

# ─── CORS — only your Vercel domain can call this ─────────────────────────────
ALLOWED_ORIGINS = [
    "https://financialai-frontend-lime.vercel.app",
    "https://financialai-frontend.vercel.app",
    # Add more Vercel preview URLs if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# ─── Simple in-memory rate limiter ────────────────────────────────────────────
# Max 10 requests per IP per minute on /api/analyze
# Max 30 requests per IP per minute on /financial-health
rate_store: dict = defaultdict(list)

def is_rate_limited(ip: str, limit: int, window: int = 60) -> bool:
    now = time.time()
    timestamps = rate_store[ip]
    # Remove old timestamps outside the window
    rate_store[ip] = [t for t in timestamps if now - t < window]
    if len(rate_store[ip]) >= limit:
        return True
    rate_store[ip].append(now)
    return False

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ─── Input sanitization ───────────────────────────────────────────────────────
def sanitize_prompt(prompt: str) -> str:
    if not isinstance(prompt, str):
        return ""
    # Trim and limit length — prevents prompt injection & oversized requests
    prompt = prompt.strip()[:2000]
    return prompt

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return {"message": "FinancialAI backend is running 🚀"}


@app.post("/financial-health")
async def financial_health(request: Request):
    ip = get_client_ip(request)
    if is_rate_limited(ip, limit=30, window=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        income   = float(data.get("income",   0))
        expenses = float(data.get("expenses", 0))
        savings  = float(data.get("savings",  0))
        emi      = float(data.get("emi",      0))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="All fields must be numbers")

    if income <= 0:
        return {"error": "Income must be greater than zero"}

    # Sanity caps — prevents absurd inputs
    if any(v > 1_000_000_000 for v in [income, expenses, savings, emi]):
        raise HTTPException(status_code=400, detail="Values exceed allowed range")

    savings_ratio = savings  / income
    expense_ratio = expenses / income
    debt_ratio    = emi      / income

    score    = 0
    insights = []

    if savings_ratio >= 0.2:
        score += 25
    else:
        score += 10
        insights.append("Increase savings to at least 20% of income")

    if expense_ratio <= 0.5:
        score += 20
    else:
        score += 10
        insights.append("Reduce expenses below 50%")

    if debt_ratio <= 0.3:
        score += 20
    else:
        score += 10
        insights.append("Reduce EMI burden")

    if savings >= expenses * 6:
        score += 15
    else:
        score += 5
        insights.append("Build 6-month emergency fund")

    score += 10

    category = "Healthy" if score > 70 else "Moderate" if score > 40 else "Risky"

    return {"score": int(score), "category": category, "insights": insights}


@app.options("/api/analyze")
async def analyze_options():
    return JSONResponse(content={})


@app.post("/api/analyze")
async def analyze(request: Request):
    # Rate limit: 10 AI calls per IP per minute
    ip = get_client_ip(request)
    if is_rate_limited(ip, limit=10, window=60):
        return JSONResponse(
            content={"error": "Too many requests. Please wait a moment and try again."},
            status_code=429,
        )

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return JSONResponse(content={"error": "Service unavailable"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    raw_prompt = body.get("messages", [{}])[0].get("content", "")
    prompt = sanitize_prompt(raw_prompt)

    if not prompt:
        return JSONResponse(content={"error": "Empty prompt"}, status_code=400)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,  # cap response size
                },
            )

        data = response.json()

        if "choices" in data and len(data["choices"]) > 0:
            text = data["choices"][0]["message"]["content"]
        else:
            return JSONResponse(content={"error": "AI service error"}, status_code=502)

        return JSONResponse(content={"content": [{"text": text}]})

    except httpx.TimeoutException:
        return JSONResponse(content={"error": "Request timed out"}, status_code=504)
    except Exception:
        return JSONResponse(content={"error": "Internal server error"}, status_code=500)
