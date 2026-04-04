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

def build_profile_context(profile: dict) -> str:
    """Build a rich financial context string from the user's saved profile."""
    if not profile:
        return ""

    monthly_income = profile.get("monthly_income", 0) or 0
    monthly_expenses = profile.get("monthly_expenses", 0) or 0
    monthly_savings = profile.get("monthly_savings", 0) or 0
    sip = profile.get("sip_amount", 0) or 0
    stocks = profile.get("stocks_value", 0) or 0
    fd = profile.get("fd_value", 0) or 0
    mf = profile.get("mutual_funds_value", 0) or 0
    nps = profile.get("nps_value", 0) or 0
    crypto = profile.get("crypto_value", 0) or 0
    real_estate = profile.get("real_estate_value", 0) or 0
    intl_stocks = profile.get("international_stocks", 0) or 0
    home_emi = profile.get("home_loan_emi", 0) or 0
    car_emi = profile.get("car_loan_emi", 0) or 0
    personal_emi = profile.get("personal_loan_emi", 0) or 0
    other_emi = profile.get("other_emi", 0) or 0
    total_emi = home_emi + car_emi + personal_emi + other_emi
    primary_goal = profile.get("primary_goal", "wealth_creation")
    retirement_age = profile.get("retirement_age", 60)
    goal_amount = profile.get("goal_amount", 0) or 0

    total_investments = stocks + mf + fd + nps + crypto + real_estate + intl_stocks
    savings_rate = (monthly_savings / monthly_income * 100) if monthly_income > 0 else 0
    emi_ratio = (total_emi / monthly_income * 100) if monthly_income > 0 else 0
    expense_ratio = (monthly_expenses / monthly_income * 100) if monthly_income > 0 else 0

    return f"""
--- USER'S FINANCIAL PROFILE (Use this to give personalized advice) ---
Monthly Income: ₹{monthly_income:,.0f}
Monthly Expenses: ₹{monthly_expenses:,.0f} ({expense_ratio:.1f}% of income)
Monthly Savings: ₹{monthly_savings:,.0f} ({savings_rate:.1f}% savings rate)
Monthly SIP: ₹{sip:,.0f}
Total EMI Burden: ₹{total_emi:,.0f}/month ({emi_ratio:.1f}% of income)
  - Home Loan EMI: ₹{home_emi:,.0f}
  - Car Loan EMI: ₹{car_emi:,.0f}
  - Personal Loan EMI: ₹{personal_emi:,.0f}
  - Other EMI: ₹{other_emi:,.0f}

Investment Portfolio (Total: ₹{total_investments:,.0f}):
  - Stocks: ₹{stocks:,.0f}
  - Mutual Funds: ₹{mf:,.0f}
  - Fixed Deposits: ₹{fd:,.0f}
  - NPS: ₹{nps:,.0f}
  - Crypto: ₹{crypto:,.0f}
  - Real Estate: ₹{real_estate:,.0f}
  - International Stocks: ₹{intl_stocks:,.0f}

Financial Goal: {primary_goal.replace('_', ' ').title()}
Target Retirement Age: {retirement_age}
Goal Amount: ₹{goal_amount:,.0f}
--- END OF PROFILE ---

Use the above data to give specific, personalized advice. Reference their actual numbers.
"""

# ─── Financial Score Calculation ─────────────────────────────────────────────
def calculate_score(profile: dict) -> dict:
    """Calculate financial health score from a profile dict. Returns score + breakdown."""
    monthly_income = float(profile.get("monthly_income", 0) or 0)
    monthly_expenses = float(profile.get("monthly_expenses", 0) or 0)
    monthly_savings = float(profile.get("monthly_savings", 0) or 0)
    sip = float(profile.get("sip_amount", 0) or 0)
    stocks = float(profile.get("stocks_value", 0) or 0)
    fd = float(profile.get("fd_value", 0) or 0)
    mf = float(profile.get("mutual_funds_value", 0) or 0)
    nps = float(profile.get("nps_value", 0) or 0)
    home_emi = float(profile.get("home_loan_emi", 0) or 0)
    car_emi = float(profile.get("car_loan_emi", 0) or 0)
    personal_emi = float(profile.get("personal_loan_emi", 0) or 0)
    other_emi = float(profile.get("other_emi", 0) or 0)
    total_emi = home_emi + car_emi + personal_emi + other_emi
    total_investments = stocks + mf + fd + nps

    if monthly_income <= 0:
        return {"score": 0, "category": "Unknown", "factors": {}, "insights": ["Please set your monthly income to calculate score."]}

    # ── Factor 1: Savings Rate (0–25 pts) ────────────────────────────
    savings_rate = monthly_savings / monthly_income
    if savings_rate >= 0.30:
        savings_score = 25
        savings_insight = f"Excellent savings rate of {savings_rate*100:.1f}%"
    elif savings_rate >= 0.20:
        savings_score = 20
        savings_insight = f"Good savings rate of {savings_rate*100:.1f}% — target 30%+"
    elif savings_rate >= 0.10:
        savings_score = 12
        savings_insight = f"Savings rate of {savings_rate*100:.1f}% is below recommended 20%"
    else:
        savings_score = 4
        savings_insight = f"Low savings rate ({savings_rate*100:.1f}%) — prioritize saving 20% of income"

    # ── Factor 2: Investment Rate (0–20 pts) ─────────────────────────
    monthly_investment_rate = sip / monthly_income if monthly_income > 0 else 0
    if monthly_investment_rate >= 0.20:
        invest_score = 20
        invest_insight = f"Strong SIP of ₹{sip:,.0f}/month ({monthly_investment_rate*100:.1f}% of income)"
    elif monthly_investment_rate >= 0.10:
        invest_score = 14
        invest_insight = f"SIP of ₹{sip:,.0f}/month — aim for 20% of income"
    elif monthly_investment_rate > 0:
        invest_score = 7
        invest_insight = f"SIP of ₹{sip:,.0f}/month is low — increase to ₹{monthly_income*0.15:,.0f}+"
    else:
        invest_score = 0
        invest_insight = f"No SIP set up — start with at least ₹{monthly_income*0.10:,.0f}/month"

    # ── Factor 3: Debt Ratio (0–20 pts) ──────────────────────────────
    emi_ratio = total_emi / monthly_income
    if emi_ratio == 0:
        debt_score = 20
        debt_insight = "Debt-free — excellent financial position"
    elif emi_ratio <= 0.20:
        debt_score = 18
        debt_insight = f"EMI burden at {emi_ratio*100:.1f}% of income — well managed"
    elif emi_ratio <= 0.35:
        debt_score = 12
        debt_insight = f"EMI burden at {emi_ratio*100:.1f}% — aim to reduce below 30%"
    elif emi_ratio <= 0.50:
        debt_score = 6
        debt_insight = f"High EMI burden at {emi_ratio*100:.1f}% — consider prepaying loans"
    else:
        debt_score = 2
        debt_insight = f"Dangerous debt load at {emi_ratio*100:.1f}% of income"

    # ── Factor 4: Emergency Fund (0–15 pts) ──────────────────────────
    monthly_need = monthly_expenses + total_emi
    emergency_months = (fd / monthly_need) if monthly_need > 0 and fd > 0 else 0
    if emergency_months >= 6:
        emerg_score = 15
        emerg_insight = f"Strong emergency fund covering {emergency_months:.1f} months"
    elif emergency_months >= 3:
        emerg_score = 10
        emerg_insight = f"Emergency fund covers {emergency_months:.1f} months — target 6 months"
    elif emergency_months >= 1:
        emerg_score = 5
        emerg_insight = f"Emergency fund of {emergency_months:.1f} months is insufficient — build to ₹{monthly_need*6:,.0f}"
    else:
        emerg_score = 0
        emerg_insight = f"No emergency fund — build ₹{monthly_need*6:,.0f} (6 months of expenses)"

    # ── Factor 5: Portfolio Diversification (0–10 pts) ───────────────
    has_equity = (stocks + mf) > 0
    has_debt = fd > 0
    has_nps = nps > 0
    has_sip = sip > 0
    diversity_count = sum([has_equity, has_debt, has_nps, has_sip])
    if diversity_count >= 4:
        div_score = 10
        div_insight = "Well diversified across equity, debt, and retirement instruments"
    elif diversity_count == 3:
        div_score = 7
        div_insight = "Good diversification — consider adding one more asset class"
    elif diversity_count == 2:
        div_score = 4
        div_insight = "Moderate diversification — spread across equity + debt + NPS"
    else:
        div_score = 1
        div_insight = "Low diversification — invest across multiple asset classes"

    # ── Factor 6: Goal Alignment (0–10 pts) ──────────────────────────
    goal_amount = float(profile.get("goal_amount", 0) or 0)
    if goal_amount > 0 and total_investments > 0:
        progress = min(total_investments / goal_amount, 1.0)
        if progress >= 0.5:
            goal_score = 10
            goal_insight = f"On track — {progress*100:.0f}% of goal amount accumulated"
        elif progress >= 0.2:
            goal_score = 6
            goal_insight = f"{progress*100:.0f}% of goal accumulated — stay consistent"
        else:
            goal_score = 3
            goal_insight = f"Early stage — {progress*100:.0f}% of ₹{goal_amount:,.0f} goal accumulated"
    elif sip > 0:
        goal_score = 6
        goal_insight = "SIP active — set a goal amount to track progress"
    else:
        goal_score = 0
        goal_insight = "Set a financial goal to measure your progress"

    total_score = savings_score + invest_score + debt_score + emerg_score + div_score + goal_score

    if total_score >= 85:
        category = "Excellent"
    elif total_score >= 70:
        category = "Healthy"
    elif total_score >= 50:
        category = "Moderate"
    elif total_score >= 30:
        category = "Risky"
    else:
        category = "Critical"

    # Key insights (top issues to fix)
    insights = []
    if savings_score < 15:
        insights.append(f"Boost savings rate — currently {savings_rate*100:.1f}%, target 20%+")
    if invest_score < 10:
        insights.append(f"Increase SIP to ₹{monthly_income*0.15:,.0f}/month (15% of income)")
    if debt_score < 12:
        insights.append(f"Reduce EMI burden — currently {emi_ratio*100:.1f}% of income")
    if emerg_score < 8:
        insights.append(f"Build emergency fund of ₹{monthly_need*6:,.0f} (6 months expenses)")
    if div_score < 5:
        insights.append("Diversify portfolio across equity, debt, NPS, and FD")

    return {
        "score": int(total_score),
        "category": category,
        "factors": {
            "savings": {"label": "Savings Rate", "score": savings_score, "max": 25, "insight": savings_insight},
            "investment": {"label": "Investment Rate", "score": invest_score, "max": 20, "insight": invest_insight},
            "debt": {"label": "Debt Management", "score": debt_score, "max": 20, "insight": debt_insight},
            "emergency": {"label": "Emergency Fund", "score": emerg_score, "max": 15, "insight": emerg_insight},
            "diversification": {"label": "Diversification", "score": div_score, "max": 10, "insight": div_insight},
            "goals": {"label": "Goal Alignment", "score": goal_score, "max": 10, "insight": goal_insight},
        },
        "insights": insights,
    }


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


# ─── NEW: Backend Financial Score API ────────────────────────────────────────
@app.options("/api/financial-score")
async def score_options():
    return JSONResponse(content={})


@app.post("/api/financial-score")
async def financial_score(request: Request):
    """
    Calculate financial health score from user's saved profile data.
    Frontend sends the profile object; backend calculates and returns score + breakdown.
    """
    ip = get_client_ip(request)
    if is_rate_limited(ip, limit=30, window=60):
        return JSONResponse(
            content={"error": "Too many requests. Please wait a moment."},
            status_code=429,
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    profile = body.get("profile", {})
    if not profile:
        return JSONResponse(content={"error": "No profile data provided"}, status_code=400)

    # Validate income is positive
    monthly_income = float(profile.get("monthly_income", 0) or 0)
    if monthly_income <= 0:
        return JSONResponse(
            content={"score": 0, "category": "Unknown", "factors": {}, "insights": ["Set your monthly income to calculate score."]},
            status_code=200,
        )

    result = calculate_score(profile)
    return JSONResponse(content=result)


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

    # ── Get conversation + optional financial profile ──────────────
    raw_messages = body.get("messages", [])
    financial_profile = body.get("financial_profile", None)  # NEW: optional profile context

    if not raw_messages:
        return JSONResponse(content={"error": "Empty messages"}, status_code=400)

    # Sanitize each message
    sanitized_messages = []
    for msg in raw_messages:
        role = msg.get("role", "user")
        content = sanitize_message(msg.get("content", ""))
        if role in ("user", "assistant") and content:
            sanitized_messages.append({"role": role, "content": content})

    if not sanitized_messages:
        return JSONResponse(content={"error": "No valid messages"}, status_code=400)

    # ── Build system prompt — inject profile if available ─────────
    system = SYSTEM_PROMPT
    if financial_profile and isinstance(financial_profile, dict):
        monthly_income = float(financial_profile.get("monthly_income", 0) or 0)
        if monthly_income > 0:
            profile_context = build_profile_context(financial_profile)
            system = system + "\n\n" + profile_context

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
                        {"role": "system", "content": system},
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
