from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os
import time
import math
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


# ═══════════════════════════════════════════════════════════════════════════════
# FINANCIAL ENGINE — pure calculation functions
# ═══════════════════════════════════════════════════════════════════════════════

def future_value_sip(monthly: float, annual_rate: float, years: int) -> float:
    """Future value of a monthly SIP at given annual return rate."""
    if monthly <= 0 or years <= 0:
        return 0.0
    r = annual_rate / 12
    n = years * 12
    if r == 0:
        return monthly * n
    return monthly * ((1 + r) ** n - 1) / r * (1 + r)


def required_sip(target: float, annual_rate: float, years: int) -> float:
    """Monthly SIP required to reach a target corpus."""
    if target <= 0 or years <= 0:
        return 0.0
    r = annual_rate / 12
    n = years * 12
    if r == 0:
        return target / n
    return target * r / ((1 + r) ** n - 1)


def retirement_corpus_needed(
    monthly_expenses: float,
    current_age: int,
    retirement_age: int,
    life_expectancy: int = 85,
    inflation_rate: float = 0.06,
    post_retirement_return: float = 0.07,
) -> float:
    """Corpus needed at retirement to sustain current lifestyle."""
    years_to_retirement = retirement_age - current_age
    years_in_retirement = life_expectancy - retirement_age
    if years_to_retirement <= 0 or years_in_retirement <= 0:
        return 0.0
    # Inflate expenses to retirement date
    future_monthly = monthly_expenses * ((1 + inflation_rate) ** years_to_retirement)
    future_annual = future_monthly * 12
    # Present value of annuity at retirement
    r = post_retirement_return
    n = years_in_retirement
    corpus = future_annual * (1 - (1 + r) ** (-n)) / r
    return corpus


def emergency_fund_needed(monthly_expenses: float, total_emi: float, months: int = 6) -> float:
    return (monthly_expenses + total_emi) * months


def lumpsum_future_value(principal: float, annual_rate: float, years: int) -> float:
    """Future value of a one-time lumpsum investment."""
    if principal <= 0 or years <= 0:
        return 0.0
    return principal * ((1 + annual_rate) ** years)


def cagr(initial: float, final: float, years: float) -> float:
    """Compound Annual Growth Rate."""
    if initial <= 0 or final <= 0 or years <= 0:
        return 0.0
    return ((final / initial) ** (1 / years)) - 1


def emi_calculator(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Monthly EMI for a loan."""
    if principal <= 0 or tenure_months <= 0:
        return 0.0
    r = annual_rate / 12
    if r == 0:
        return principal / tenure_months
    return principal * r * (1 + r) ** tenure_months / ((1 + r) ** tenure_months - 1)


def calculate_financial_metrics(profile: dict) -> dict:
    """
    Run all financial calculations on a profile.
    Returns a rich dict of calculated metrics used by score, recommendations, and AI.
    """
    monthly_income = float(profile.get("monthly_income", 0) or 0)
    monthly_expenses = float(profile.get("monthly_expenses", 0) or 0)
    monthly_savings = float(profile.get("monthly_savings", 0) or 0)
    sip = float(profile.get("sip_amount", 0) or 0)
    stocks = float(profile.get("stocks_value", 0) or 0)
    fd = float(profile.get("fd_value", 0) or 0)
    mf = float(profile.get("mutual_funds_value", 0) or 0)
    nps = float(profile.get("nps_value", 0) or 0)
    crypto = float(profile.get("crypto_value", 0) or 0)
    real_estate = float(profile.get("real_estate_value", 0) or 0)
    intl_stocks = float(profile.get("international_stocks", 0) or 0)
    home_emi = float(profile.get("home_loan_emi", 0) or 0)
    car_emi = float(profile.get("car_loan_emi", 0) or 0)
    personal_emi = float(profile.get("personal_loan_emi", 0) or 0)
    other_emi = float(profile.get("other_emi", 0) or 0)
    retirement_age = int(profile.get("retirement_age", 60) or 60)
    goal_amount = float(profile.get("goal_amount", 0) or 0)
    current_age = int(profile.get("current_age", 30) or 30)

    total_emi = home_emi + car_emi + personal_emi + other_emi
    total_investments = stocks + mf + fd + nps + crypto + real_estate + intl_stocks
    total_liquid = stocks + mf + fd + nps  # excluding illiquid assets
    years_to_retirement = max(retirement_age - current_age, 1)

    # Rates
    savings_rate = (monthly_savings / monthly_income) if monthly_income > 0 else 0
    emi_ratio = (total_emi / monthly_income) if monthly_income > 0 else 0
    expense_ratio = (monthly_expenses / monthly_income) if monthly_income > 0 else 0
    sip_rate = (sip / monthly_income) if monthly_income > 0 else 0
    monthly_surplus = monthly_income - monthly_expenses - total_emi - monthly_savings

    # Emergency fund
    emerg_needed = emergency_fund_needed(monthly_expenses, total_emi)
    emerg_current = fd  # FD treated as emergency fund proxy
    emerg_gap = max(emerg_needed - emerg_current, 0)
    emerg_months_covered = (fd / (monthly_expenses + total_emi)) if (monthly_expenses + total_emi) > 0 else 0

    # Retirement
    corpus_needed = retirement_corpus_needed(
        monthly_expenses, current_age, retirement_age
    )
    sip_needed_for_retirement = required_sip(
        corpus_needed - total_liquid, annual_rate=0.12, years=years_to_retirement
    ) if corpus_needed > total_liquid else 0
    sip_gap = max(sip_needed_for_retirement - sip, 0)

    # SIP projection (12% assumed)
    sip_10yr = future_value_sip(sip, 0.12, 10) if sip > 0 else 0
    sip_at_retirement = future_value_sip(sip, 0.12, years_to_retirement) if sip > 0 else 0

    # Recommended SIP (15% of income is minimum)
    recommended_sip = max(monthly_income * 0.15, sip_needed_for_retirement)

    # Goal progress
    goal_progress = (total_investments / goal_amount * 100) if goal_amount > 0 else 0

    # Ideal emergency fund months
    ideal_emerg_months = 6

    return {
        "monthly_income": monthly_income,
        "monthly_expenses": monthly_expenses,
        "monthly_savings": monthly_savings,
        "monthly_surplus": monthly_surplus,
        "total_emi": total_emi,
        "total_investments": total_investments,
        "total_liquid": total_liquid,
        "sip": sip,
        "fd": fd,
        # Rates
        "savings_rate": savings_rate,
        "emi_ratio": emi_ratio,
        "expense_ratio": expense_ratio,
        "sip_rate": sip_rate,
        # Emergency fund
        "emerg_needed": emerg_needed,
        "emerg_current": emerg_current,
        "emerg_gap": emerg_gap,
        "emerg_months_covered": emerg_months_covered,
        # Retirement
        "years_to_retirement": years_to_retirement,
        "corpus_needed": corpus_needed,
        "sip_needed_for_retirement": sip_needed_for_retirement,
        "sip_gap": sip_gap,
        "sip_at_retirement": sip_at_retirement,
        "sip_10yr": sip_10yr,
        "recommended_sip": recommended_sip,
        # Goal
        "goal_amount": goal_amount,
        "goal_progress": goal_progress,
        "retirement_age": retirement_age,
        "current_age": current_age,
    }


def build_calculations_context(m: dict) -> str:
    """Build a pre-calculated context string to inject into AI prompt."""
    lines = [
        "--- PRE-CALCULATED FINANCIAL METRICS (Use these exact numbers in your response) ---",
        f"Monthly Surplus (after all deductions): ₹{m['monthly_surplus']:,.0f}",
        f"Savings Rate: {m['savings_rate']*100:.1f}% of income",
        f"EMI Burden: {m['emi_ratio']*100:.1f}% of income",
        f"SIP Rate: {m['sip_rate']*100:.1f}% of income",
        "",
        "Emergency Fund:",
        f"  - Required (6 months): ₹{m['emerg_needed']:,.0f}",
        f"  - Current (FD): ₹{m['emerg_current']:,.0f}",
        f"  - Gap: ₹{m['emerg_gap']:,.0f}",
        f"  - Months covered: {m['emerg_months_covered']:.1f} months",
        "",
        "Retirement Planning:",
        f"  - Years to retirement: {m['years_to_retirement']}",
        f"  - Corpus needed at retirement: ₹{m['corpus_needed']:,.0f}",
        f"  - Current SIP projection at retirement: ₹{m['sip_at_retirement']:,.0f}",
        f"  - Additional SIP needed: ₹{m['sip_gap']:,.0f}/month",
        f"  - Recommended minimum SIP: ₹{m['recommended_sip']:,.0f}/month",
        "",
        "10-Year SIP Projection (at 12% returns):",
        f"  - Current SIP of ₹{m['sip']:,.0f}/month grows to: ₹{m['sip_10yr']:,.0f}",
    ]
    if m["goal_amount"] > 0:
        lines += [
            "",
            f"Goal Progress: {m['goal_progress']:.1f}% of ₹{m['goal_amount']:,.0f} target",
        ]
    lines.append("--- END CALCULATIONS ---")
    lines.append("Use these exact calculated numbers. Do NOT guess or estimate — the numbers above are mathematically correct.")
    return "\n".join(lines)


def build_profile_context(profile: dict) -> str:
    """Build profile + calculations context for AI."""
    m = calculate_financial_metrics(profile)

    monthly_income = m["monthly_income"]
    monthly_expenses = m["monthly_expenses"]
    monthly_savings = m["monthly_savings"]
    total_emi = m["total_emi"]

    sip = float(profile.get("sip_amount", 0) or 0)
    stocks = float(profile.get("stocks_value", 0) or 0)
    fd = float(profile.get("fd_value", 0) or 0)
    mf = float(profile.get("mutual_funds_value", 0) or 0)
    nps = float(profile.get("nps_value", 0) or 0)
    crypto = float(profile.get("crypto_value", 0) or 0)
    real_estate = float(profile.get("real_estate_value", 0) or 0)
    intl_stocks = float(profile.get("international_stocks", 0) or 0)
    home_emi = float(profile.get("home_loan_emi", 0) or 0)
    car_emi = float(profile.get("car_loan_emi", 0) or 0)
    personal_emi = float(profile.get("personal_loan_emi", 0) or 0)
    other_emi = float(profile.get("other_emi", 0) or 0)
    primary_goal = profile.get("primary_goal", "wealth_creation")
    retirement_age = m["retirement_age"]
    goal_amount = m["goal_amount"]

    profile_ctx = f"""
--- USER'S FINANCIAL PROFILE ---
Monthly Income: ₹{monthly_income:,.0f}
Monthly Expenses: ₹{monthly_expenses:,.0f} ({m['expense_ratio']*100:.1f}% of income)
Monthly Savings: ₹{monthly_savings:,.0f} ({m['savings_rate']*100:.1f}% savings rate)
Monthly SIP: ₹{sip:,.0f}
Total EMI: ₹{total_emi:,.0f}/month ({m['emi_ratio']*100:.1f}% of income)
  - Home Loan: ₹{home_emi:,.0f} | Car: ₹{car_emi:,.0f} | Personal: ₹{personal_emi:,.0f} | Other: ₹{other_emi:,.0f}

Portfolio (Total: ₹{m['total_investments']:,.0f}):
  - Stocks: ₹{stocks:,.0f} | Mutual Funds: ₹{mf:,.0f} | FD: ₹{fd:,.0f}
  - NPS: ₹{nps:,.0f} | Crypto: ₹{crypto:,.0f} | Real Estate: ₹{real_estate:,.0f} | Intl: ₹{intl_stocks:,.0f}

Goal: {primary_goal.replace('_', ' ').title()} | Retirement Age: {retirement_age} | Target: ₹{goal_amount:,.0f}
--- END PROFILE ---
"""

    calc_ctx = build_calculations_context(m)
    return profile_ctx + "\n" + calc_ctx


# ─── Financial Score Calculation ─────────────────────────────────────────────
def calculate_score(profile: dict) -> dict:
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

    m = calculate_financial_metrics(profile)

    # Factor 1: Savings Rate (0–25 pts)
    sr = m["savings_rate"]
    if sr >= 0.30:   savings_score, savings_insight = 25, f"Excellent savings rate of {sr*100:.1f}%"
    elif sr >= 0.20: savings_score, savings_insight = 20, f"Good savings rate of {sr*100:.1f}% — target 30%+"
    elif sr >= 0.10: savings_score, savings_insight = 12, f"Savings rate of {sr*100:.1f}% is below recommended 20%"
    else:            savings_score, savings_insight = 4,  f"Low savings rate ({sr*100:.1f}%) — prioritize saving 20% of income"

    # Factor 2: Investment Rate (0–20 pts)
    sir = m["sip_rate"]
    if sir >= 0.20:   invest_score, invest_insight = 20, f"Strong SIP of ₹{sip:,.0f}/month ({sir*100:.1f}% of income)"
    elif sir >= 0.10: invest_score, invest_insight = 14, f"SIP of ₹{sip:,.0f}/month — aim for 20% of income"
    elif sir > 0:     invest_score, invest_insight = 7,  f"SIP of ₹{sip:,.0f}/month is low — increase to ₹{monthly_income*0.15:,.0f}+"
    else:             invest_score, invest_insight = 0,  f"No SIP — start with at least ₹{monthly_income*0.10:,.0f}/month"

    # Factor 3: Debt Ratio (0–20 pts)
    er = m["emi_ratio"]
    if er == 0:      debt_score, debt_insight = 20, "Debt-free — excellent financial position"
    elif er <= 0.20: debt_score, debt_insight = 18, f"EMI burden at {er*100:.1f}% — well managed"
    elif er <= 0.35: debt_score, debt_insight = 12, f"EMI burden at {er*100:.1f}% — aim to reduce below 30%"
    elif er <= 0.50: debt_score, debt_insight = 6,  f"High EMI burden at {er*100:.1f}% — consider prepaying loans"
    else:            debt_score, debt_insight = 2,  f"Dangerous debt load at {er*100:.1f}% of income"

    # Factor 4: Emergency Fund (0–15 pts)
    emc = m["emerg_months_covered"]
    emerg_needed = m["emerg_needed"]
    if emc >= 6:   emerg_score, emerg_insight = 15, f"Strong emergency fund covering {emc:.1f} months"
    elif emc >= 3: emerg_score, emerg_insight = 10, f"Emergency fund covers {emc:.1f} months — target 6 months"
    elif emc >= 1: emerg_score, emerg_insight = 5,  f"Emergency fund of {emc:.1f} months — build to ₹{emerg_needed:,.0f}"
    else:          emerg_score, emerg_insight = 0,  f"No emergency fund — build ₹{emerg_needed:,.0f} (6 months of expenses)"

    # Factor 5: Diversification (0–10 pts)
    diversity_count = sum([(stocks + mf) > 0, fd > 0, nps > 0, sip > 0])
    if diversity_count >= 4:   div_score, div_insight = 10, "Well diversified across equity, debt, and retirement"
    elif diversity_count == 3: div_score, div_insight = 7,  "Good diversification — consider adding one more asset class"
    elif diversity_count == 2: div_score, div_insight = 4,  "Moderate diversification — spread across equity + debt + NPS"
    else:                      div_score, div_insight = 1,  "Low diversification — invest across multiple asset classes"

    # Factor 6: Goal Alignment (0–10 pts)
    goal_amount = float(profile.get("goal_amount", 0) or 0)
    if goal_amount > 0 and total_investments > 0:
        progress = min(total_investments / goal_amount, 1.0)
        if progress >= 0.5:   goal_score, goal_insight = 10, f"On track — {progress*100:.0f}% of goal accumulated"
        elif progress >= 0.2: goal_score, goal_insight = 6,  f"{progress*100:.0f}% of goal — stay consistent"
        else:                  goal_score, goal_insight = 3,  f"Early stage — {progress*100:.0f}% of ₹{goal_amount:,.0f} goal"
    elif sip > 0: goal_score, goal_insight = 6, "SIP active — set a goal amount to track progress"
    else:         goal_score, goal_insight = 0, "Set a financial goal to measure your progress"

    total_score = savings_score + invest_score + debt_score + emerg_score + div_score + goal_score

    if total_score >= 85:   category = "Excellent"
    elif total_score >= 70: category = "Healthy"
    elif total_score >= 50: category = "Moderate"
    elif total_score >= 30: category = "Risky"
    else:                   category = "Critical"

    insights = []
    if savings_score < 15: insights.append(f"Boost savings rate — currently {sr*100:.1f}%, target 20%+")
    if invest_score < 10:  insights.append(f"Increase SIP to ₹{monthly_income*0.15:,.0f}/month (15% of income)")
    if debt_score < 12:    insights.append(f"Reduce EMI burden — currently {er*100:.1f}% of income")
    if emerg_score < 8:    insights.append(f"Build emergency fund of ₹{emerg_needed:,.0f} (6 months expenses)")
    if div_score < 5:      insights.append("Diversify portfolio across equity, debt, NPS, and FD")

    return {
        "score": int(total_score),
        "category": category,
        "factors": {
            "savings":       {"label": "Savings Rate",      "score": savings_score, "max": 25, "insight": savings_insight},
            "investment":    {"label": "Investment Rate",   "score": invest_score,  "max": 20, "insight": invest_insight},
            "debt":          {"label": "Debt Management",   "score": debt_score,    "max": 20, "insight": debt_insight},
            "emergency":     {"label": "Emergency Fund",    "score": emerg_score,   "max": 15, "insight": emerg_insight},
            "diversification":{"label": "Diversification",  "score": div_score,     "max": 10, "insight": div_insight},
            "goals":         {"label": "Goal Alignment",    "score": goal_score,    "max": 10, "insight": goal_insight},
        },
        "insights": insights,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def home():
    return {"message": "FinancialAI backend is running 🚀"}


@app.post("/financial-health")
async def financial_health(request: Request):
    ip = get_client_ip(request)
    if is_rate_limited(ip, limit=30, window=60):
        raise HTTPException(status_code=429, detail="Too many requests.")
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
    savings_ratio = savings / income
    expense_ratio = expenses / income
    debt_ratio    = emi / income
    score = 0
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


# ─── Financial Score ──────────────────────────────────────────────────────────
@app.options("/api/financial-score")
async def score_options():
    return JSONResponse(content={})


@app.post("/api/financial-score")
async def financial_score(request: Request):
    ip = get_client_ip(request)
    if is_rate_limited(ip, limit=30, window=60):
        return JSONResponse(content={"error": "Too many requests."}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    profile = body.get("profile", {})
    if not profile:
        return JSONResponse(content={"error": "No profile data provided"}, status_code=400)

    monthly_income = float(profile.get("monthly_income", 0) or 0)
    if monthly_income <= 0:
        return JSONResponse(
            content={"score": 0, "category": "Unknown", "factors": {}, "insights": ["Set your monthly income to calculate score."]},
            status_code=200,
        )

    result = calculate_score(profile)
    return JSONResponse(content=result)


# ─── Recommendations (calculated, not AI-guessed) ────────────────────────────
@app.options("/api/recommendations")
async def rec_options():
    return JSONResponse(content={})


@app.post("/api/recommendations")
async def recommendations(request: Request):
    """
    Returns calculated, specific recommendations based on the user's profile.
    No AI involved — pure math.
    """
    ip = get_client_ip(request)
    if is_rate_limited(ip, limit=30, window=60):
        return JSONResponse(content={"error": "Too many requests."}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    profile = body.get("profile", {})
    if not profile:
        return JSONResponse(content={"error": "No profile data provided"}, status_code=400)

    m = calculate_financial_metrics(profile)
    recs = []

    # Emergency fund
    if m["emerg_gap"] > 0:
        months_to_build = math.ceil(m["emerg_gap"] / m["monthly_surplus"]) if m["monthly_surplus"] > 0 else None
        recs.append({
            "category": "emergency_fund",
            "priority": "high",
            "title": "Build Emergency Fund",
            "detail": f"You need ₹{m['emerg_gap']:,.0f} more to reach a 6-month emergency fund (₹{m['emerg_needed']:,.0f} total).",
            "action": f"Set aside ₹{min(m['emerg_gap'], m['monthly_surplus'] * 0.5):,.0f}/month into an FD or liquid fund.",
            "timeline": f"~{months_to_build} months" if months_to_build else "Start immediately",
            "amount": m["emerg_gap"],
        })

    # SIP / investment
    if m["sip_gap"] > 0:
        recs.append({
            "category": "sip",
            "priority": "high",
            "title": "Increase Monthly SIP",
            "detail": f"To retire at {m['retirement_age']} with ₹{m['corpus_needed']:,.0f} corpus, you need ₹{m['sip_needed_for_retirement']:,.0f}/month SIP. Current: ₹{m['sip']:,.0f}/month. Gap: ₹{m['sip_gap']:,.0f}/month.",
            "action": f"Increase SIP by ₹{m['sip_gap']:,.0f}/month into diversified equity mutual funds.",
            "timeline": "This month",
            "amount": m["sip_gap"],
        })
    elif m["sip"] == 0:
        recs.append({
            "category": "sip",
            "priority": "high",
            "title": "Start a Monthly SIP",
            "detail": f"No SIP detected. To build wealth, start with at least ₹{m['recommended_sip']:,.0f}/month (15% of income).",
            "action": f"Start SIP of ₹{m['recommended_sip']:,.0f}/month in a Nifty 50 index fund.",
            "timeline": "This week",
            "amount": m["recommended_sip"],
        })

    # Savings rate
    if m["savings_rate"] < 0.20:
        target_savings = m["monthly_income"] * 0.20
        recs.append({
            "category": "savings",
            "priority": "medium",
            "title": "Increase Savings Rate",
            "detail": f"Your savings rate is {m['savings_rate']*100:.1f}%. Target is 20% (₹{target_savings:,.0f}/month).",
            "action": f"Reduce discretionary expenses by ₹{target_savings - m['monthly_savings']:,.0f}/month to hit 20% savings.",
            "timeline": "Next 3 months",
            "amount": target_savings - m["monthly_savings"],
        })

    # Debt
    if m["emi_ratio"] > 0.35:
        recs.append({
            "category": "debt",
            "priority": "high",
            "title": "Reduce Debt Burden",
            "detail": f"EMI is {m['emi_ratio']*100:.1f}% of income — above the safe 35% threshold.",
            "action": "Prepay the highest-interest loan first (personal loan > car loan > home loan).",
            "timeline": "Start this month",
            "amount": 0,
        })

    # Diversification
    sip = float(profile.get("sip_amount", 0) or 0)
    stocks = float(profile.get("stocks_value", 0) or 0)
    mf_val = float(profile.get("mutual_funds_value", 0) or 0)
    fd = float(profile.get("fd_value", 0) or 0)
    nps = float(profile.get("nps_value", 0) or 0)
    diversity_count = sum([(stocks + mf_val) > 0, fd > 0, nps > 0, sip > 0])
    if diversity_count < 3:
        recs.append({
            "category": "diversification",
            "priority": "medium",
            "title": "Diversify Portfolio",
            "detail": "Portfolio is concentrated. Spread across equity, debt, and NPS for better risk management.",
            "action": "Add NPS (saves ₹50,000 extra under 80CCD(1B)) and a debt fund for stability.",
            "timeline": "Next 2 months",
            "amount": 0,
        })

    # Surplus utilization
    if m["monthly_surplus"] > 5000:
        recs.append({
            "category": "surplus",
            "priority": "low",
            "title": "Put Surplus to Work",
            "detail": f"You have ₹{m['monthly_surplus']:,.0f}/month surplus sitting idle.",
            "action": f"Invest ₹{m['monthly_surplus'] * 0.7:,.0f} in SIP and keep ₹{m['monthly_surplus'] * 0.3:,.0f} as buffer.",
            "timeline": "This month",
            "amount": m["monthly_surplus"] * 0.7,
        })

    return JSONResponse(content={
        "recommendations": recs,
        "metrics": {
            "savings_rate": round(m["savings_rate"] * 100, 1),
            "emi_ratio": round(m["emi_ratio"] * 100, 1),
            "emerg_months": round(m["emerg_months_covered"], 1),
            "corpus_needed": round(m["corpus_needed"]),
            "sip_at_retirement": round(m["sip_at_retirement"]),
            "monthly_surplus": round(m["monthly_surplus"]),
        }
    })


# ─── Simulation ───────────────────────────────────────────────────────────────
@app.options("/api/simulate")
async def simulate_options():
    return JSONResponse(content={})


@app.post("/api/simulate")
async def simulate(request: Request):
    """
    Simulate 'what if' scenarios — SIP projections, retirement corpus, lumpsum growth.
    """
    ip = get_client_ip(request)
    if is_rate_limited(ip, limit=30, window=60):
        return JSONResponse(content={"error": "Too many requests."}, status_code=429)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    sim_type = body.get("type", "sip")  # sip | lumpsum | retirement

    if sim_type == "sip":
        monthly = float(body.get("monthly_sip", 0) or 0)
        years = int(body.get("years", 10) or 10)
        rate = float(body.get("annual_return", 0.12) or 0.12)
        invested = monthly * years * 12
        corpus = future_value_sip(monthly, rate, years)
        gain = corpus - invested
        return JSONResponse(content={
            "type": "sip",
            "monthly_sip": monthly,
            "years": years,
            "annual_return_pct": rate * 100,
            "total_invested": round(invested),
            "future_value": round(corpus),
            "total_gain": round(gain),
            "wealth_multiple": round(corpus / invested, 2) if invested > 0 else 0,
        })

    elif sim_type == "lumpsum":
        principal = float(body.get("principal", 0) or 0)
        years = int(body.get("years", 10) or 10)
        rate = float(body.get("annual_return", 0.12) or 0.12)
        fv = lumpsum_future_value(principal, rate, years)
        return JSONResponse(content={
            "type": "lumpsum",
            "principal": principal,
            "years": years,
            "annual_return_pct": rate * 100,
            "future_value": round(fv),
            "total_gain": round(fv - principal),
            "wealth_multiple": round(fv / principal, 2) if principal > 0 else 0,
        })

    elif sim_type == "retirement":
        monthly_expenses = float(body.get("monthly_expenses", 0) or 0)
        current_age = int(body.get("current_age", 30) or 30)
        retirement_age = int(body.get("retirement_age", 60) or 60)
        current_sip = float(body.get("current_sip", 0) or 0)
        current_corpus = float(body.get("current_corpus", 0) or 0)
        years = max(retirement_age - current_age, 1)

        corpus_needed = retirement_corpus_needed(monthly_expenses, current_age, retirement_age)
        sip_corpus = future_value_sip(current_sip, 0.12, years)
        lump_corpus = lumpsum_future_value(current_corpus, 0.12, years)
        total_projected = sip_corpus + lump_corpus
        shortfall = max(corpus_needed - total_projected, 0)
        req_sip = required_sip(shortfall, 0.12, years) if shortfall > 0 else 0

        return JSONResponse(content={
            "type": "retirement",
            "current_age": current_age,
            "retirement_age": retirement_age,
            "years_to_retirement": years,
            "corpus_needed": round(corpus_needed),
            "projected_corpus": round(total_projected),
            "shortfall": round(shortfall),
            "additional_sip_needed": round(req_sip),
            "on_track": shortfall == 0,
        })

    else:
        return JSONResponse(content={"error": f"Unknown simulation type: {sim_type}"}, status_code=400)


# ─── AI Analyze (calculation-aware) ──────────────────────────────────────────
@app.options("/api/analyze")
async def analyze_options():
    return JSONResponse(content={})


@app.post("/api/analyze")
async def analyze(request: Request):
    ip = get_client_ip(request)
    if is_rate_limited(ip, limit=20, window=60):
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

    raw_messages = body.get("messages", [])
    financial_profile = body.get("financial_profile", None)

    if not raw_messages:
        return JSONResponse(content={"error": "Empty messages"}, status_code=400)

    sanitized_messages = []
    for msg in raw_messages:
        role = msg.get("role", "user")
        content = sanitize_message(msg.get("content", ""))
        if role in ("user", "assistant") and content:
            sanitized_messages.append({"role": role, "content": content})

    if not sanitized_messages:
        return JSONResponse(content={"error": "No valid messages"}, status_code=400)

    # Build system prompt with profile + pre-calculated metrics
    system = SYSTEM_PROMPT
    if financial_profile and isinstance(financial_profile, dict):
        monthly_income = float(financial_profile.get("monthly_income", 0) or 0)
        if monthly_income > 0:
            system = system + "\n\n" + build_profile_context(financial_profile)

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
