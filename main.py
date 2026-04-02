@app.post("/financial-health")
def financial_health(data: dict):
    income = data.get("income", 0)
    expenses = data.get("expenses", 0)
    savings = data.get("savings", 0)
    emi = data.get("emi", 0)

    if income == 0:
        return {"error": "Income cannot be zero"}

    savings_ratio = savings / income
    expense_ratio = expenses / income
    debt_ratio = emi / income

    score = 0
    insights = []

    # Savings (25)
    if savings_ratio >= 0.2:
        score += 25
    elif savings_ratio >= 0.1:
        score += 15
        insights.append("Increase savings to at least 20% of income")
    else:
        score += 5
        insights.append("Your savings are too low")

    # Expenses (20)
    if expense_ratio <= 0.5:
        score += 20
    elif expense_ratio <= 0.7:
        score += 10
        insights.append("Reduce expenses below 50%")
    else:
        score += 5
        insights.append("Expenses are too high")

    # Debt (20)
    if debt_ratio <= 0.2:
        score += 20
    elif debt_ratio <= 0.4:
        score += 10
        insights.append("Reduce EMI burden")
    else:
        score += 5
        insights.append("High debt risk")

    # Emergency fund (15)
    if savings >= expenses * 6:
        score += 15
    else:
        score += 5
        insights.append("Build emergency fund (6 months)")

    # Investment (20 default for now)
    score += 10

    category = "Healthy" if score > 70 else "Moderate" if score > 40 else "Risky"

    return {
        "score": score,
        "category": category,
        "insights": insights
    }