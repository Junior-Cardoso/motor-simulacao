"""Fatos da série já calculada. A explicação não pode trocar o número."""


def _metric_value(row: dict, plan: dict) -> int:
    metric = plan.get("metric_id")
    if metric == "vendas_realizadas":
        return row["closed_count"]
    if metric == "sentimento":
        return row["sentiment_score"]
    if metric == "objecoes":
        return row["objection_count"]
    return row["total_value"]


def fact_sheet(plan: dict, evidence: dict) -> dict | None:
    rows = evidence.get("dataset") or []
    if not rows:
        return None
    weeks = [{"period": row["period"], "value": _metric_value(row, plan)} for row in rows]
    values = [item["value"] for item in weeks]
    simulation = evidence.get("simulation") or {}
    return {
        "metric": plan.get("metric_label"),
        "filters": plan.get("filters") or [],
        "time_range": plan.get("time_range"),
        "weeks": weeks,
        "quietest_week": min(values),
        "busiest_week": max(values),
        "first_week": values[0],
        "last_week": values[-1],
        "baseline": simulation.get("baseline", sum(values)),
        "probability": simulation.get("probability"),
        "probability_is_locked": True,
        "cause_in_series": False,
    }


def plain_why(sheet: dict) -> str:
    percent = ""
    if sheet.get("probability") is not None:
        percent = f"A probabilidade de {round(sheet['probability'] * 100)}% já está fechada e não muda. "
    if sheet["quietest_week"] == sheet["busiest_week"]:
        spread = "As semanas tiveram o mesmo valor, então esta série não mostra oscilação."
    else:
        spread = (
            f"A semana mais fraca teve {sheet['quietest_week']} e a mais forte teve {sheet['busiest_week']}. "
            "O número sai dessa diferença. A série mostra o tamanho da oscilação, não a causa de cada semana."
        )
    return f"Por quê: {percent}{spread}"
