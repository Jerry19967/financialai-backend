from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "FinancialAI backend is running 🚀"}

@app.post("/financial-health")
def financial_health(data: dict):
    income = float(data.get("income", 0))
    expenses = float(data.get("expenses", 0))
    savings = float(data.get("savings", 0))
    emi = float(data.get("emi", 0))
    if income <= 0:
        return {"error": "Income must be greater than zero"}
    savings_ratio = savings / income
    expense_ratio = expenses / income
    debt_ratio = emi / income
    score = 0
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
    if score > 70:
        category = "Healthy"
    elif score > 40:
        category = "Moderate"
    else:
        category = "Risky"
    return {"score": int(score), "category": category, "insights": insights}

@app.post("/api/analyze")
async def analyze(request: Request):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set")
    body = await request.json()
    prompt = body["messages"][0]["content"]
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return {"content": [{"text": text}]}
