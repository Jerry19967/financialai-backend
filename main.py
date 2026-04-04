from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "FinancialAI backend is running 🚀"}

@app.post("/financial-health")
def financial_health(data: dict):
    try:
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

        return {
            "score": int(score),
            "category": category,
            "insights": insights
        }

    except Exception as e:
        return {"error": str(e)}

@app.options("/api/analyze")
async def analyze_options():
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )

@app.post("/api/analyze")
async def analyze(request: Request):
    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        return JSONResponse(
            content={"error": "GROQ_API_KEY not set"},
            status_code=500,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    try:
        body = await request.json()
        prompt = body.get("messages", [{}])[0].get("content", "")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama3-8b-8192",
                    "messages": [{"role": "user", "content": prompt}]
                },
            )

        data = response.json()
        print("GROQ RESPONSE:", data)

        if "choices" in data and len(data["choices"]) > 0:
            text = data["choices"][0]["message"]["content"]
        else:
            return JSONResponse(
                content={"error": "Unexpected Groq response", "full": data},
                status_code=500,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        return JSONResponse(
            content={"content": [{"text": text}]},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
        )

    except Exception as e:
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
            headers={"Access-Control-Allow-Origin": "*"},
        )
