from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os

app = FastAPI()

# ✅ CORS FIX (important)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Health Check
@app.get("/")
def home():
    return {"message": "FinancialAI backend is running 🚀"}


# ✅ Financial Health API (unchanged, just safer)
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


# ✅ OPTIONS handler (CORS preflight)
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


# ✅ FINAL GEMINI API (FULLY SAFE)
@app.post("/api/analyze")
async def analyze(request: Request):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return JSONResponse(
            content={"error": "GEMINI_API_KEY not set"},
            status_code=500,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    try:
        body = await request.json()
        prompt = body.get("messages", [{}])[0].get("content", "")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [
                        {"parts": [{"text": prompt}]}
                    ]
                },
            )

        # ✅ ALWAYS log raw response (critical for debugging)
        raw_text = response.text
        print("RAW GEMINI RESPONSE:", raw_text)

        # ✅ Try parsing JSON safely
        try:
            data = response.json()
        except Exception:
            return JSONResponse(
                content={
                    "error": "Invalid JSON from Gemini",
                    "raw": raw_text
                },
                status_code=500,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        # ✅ SAFE extraction (no crash)
        if "candidates" in data and len(data["candidates"]) > 0:
            parts = data["candidates"][0].get("content", {}).get("parts", [])
            text = parts[0].get("text", "") if parts else "No response from AI"
        else:
            return JSONResponse(
                content={
                    "error": "Unexpected Gemini response",
                    "full_response": data
                },
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
