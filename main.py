from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os
import time
from collections import defaultdict

app = FastAPI()

ALLOWED_ORIGINS = [
    "https://financialai-frontend-lime.vercel.app",
    "https://financialai-frontend.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# ─── System prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are FinHealth AI, an expert Indian personal finance advisor built into the FinHealth AI platform.

Your expertise covers:
- Mutual funds, SIPs, index funds, stocks, PPF, NPS, FDs
- Indian tax laws: Section 80C, 80D, HRA, home loan deductions, old vs new regime
- Insurance: term plans, health insurance, ULIP analysis, IRR calculation
- Loans: home loans, personal loans, EMI calculations, prepayment strategies
- Financial health: savings rate, emergency fund, debt management
- Goal planning: retirement corpus, child education, home purchase

Your style:
- Be specific and actionable — give actual numbers, not vague advice
- Use Indian context — rupees (₹), Indian regulations, Indian market instruments
- Be concise but thorough — use bullet points when listing multiple points
- Be friendly and conversational, like a trusted financial advisor
- Always mention if something needs professional consultation for legal/tax matters

Always end responses with a one-line disclaimer: "📌 This is informational only, not personalized financial advice."
"""

rate_store: dict = defaultdict(list)

def is_rate_limited(ip: str, limit: int, window: int = 60) -> bool:
    now = time.time()
    rate_store[ip] = [t for t in rate_store[ip] if now - t < window]
    if len(rate_store[ip]) >= limit:
        return True
    rate_store[ip].append(now)
    return False

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def sanitize_message(content: str) -> str:
    if not isinstance(content, str):
        return ""
    return content.strip()[:2000]

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

    if any(v > 1_000_000_000 for v in [income, expenses, savings, emi]):
        raise HTTPException(status_code=400, detail="Values exceed allowed range")

    savings_ratio = savings  / income
    expense_ratio = expenses / income
    debt_ratio    = emi      / income
    score    = 0
    insights = []

    if savings_ratio >= 0.2: score += 25
    else: score += 10; insights.append("Increase savings to at least 20% of income")

    if expense_ratio <= 0.5: score += 20
    else: score += 10; insights.append("Reduce expenses below 50%")

    if debt_ratio <= 0.3: score += 20
    else: score += 10; insights.append("Reduce EMI burden")

    if savings >= expenses * 6: score += 15
    else: score += 5; insights.append("Build 6-month emergency fund")

    score += 10
    category = "Healthy" if score > 70 else "Moderate" if score > 40 else "Risky"
    return {"score": int(score), "category": category, "insights": insights}


@app.options("/api/analyze")
async def analyze_options():
    return JSONResponse(content={})


@app.post("/api/analyze")
async def analyze(request: Request):
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

    # ── Get full conversation history from frontend ──
    raw_messages = body.get("messages", [])
    if not raw_messages:
        return JSONResponse(content={"error": "Empty messages"}, status_code=400)

    # Sanitize each message and keep role + content
    sanitized_messages = []
    for msg in raw_messages:
        role = msg.get("role", "user")
        content = sanitize_message(msg.get("content", ""))
        if role in ("user", "assistant") and content:
            sanitized_messages.append({"role": role, "content": content})

    if not sanitized_messages:
        return JSONResponse(content={"error": "No valid messages"}, status_code=400)

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
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *sanitized_messages,
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.7,
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
