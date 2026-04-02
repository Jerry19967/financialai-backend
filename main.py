from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create app
app = FastAPI()

# Enable CORS (important for frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
def home():
    return {"message": "FinancialAI backend is running 🚀"}


# Financial Health API
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

        # Savings (25)
        if savings_ratio >= 0.2:
            score += 25
        else:
            score += 10
            insights.append("Increase savings to at least 20% of income")

        # Expenses (20)
        if expense_ratio <= 0.5:
            score += 20
        else:
            score += 10
            insights.append("Reduce expenses below 50%")

        # Debt (20)
        if debt_ratio <= 0.3:
            score += 20
        else:
            score += 10
            insights.append("Reduce EMI burden")

        # Emergency fund (15)
        if savings >= expenses * 6:
            score += 15
        else:
            score += 5
            insights.append("Build 6-month emergency fund")

        # Investment (20 placeholder)
        score += 10

        category = "Healthy" if score > 70 else "Moderate" if score > 40 else "Risky"

        return {
            "score": int(score),
            "category": category,
            "insights": insights
        }

    except Exception as e:
        return {"error": str(e)}
