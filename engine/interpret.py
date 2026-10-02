"""Traduz a frase na ficha. A chamada de modelo, se existir, entra antes das regras."""

import re

from engine.catalog import METRICS
from engine.model import call_model

PRODUCTS = (
    (re.compile(r"garrafa", re.I), "Garrafas"),
    (re.compile(r"copo", re.I), "Copos"),
)

PHASES = (
    (re.compile(r"venda realizada|vendas realizadas", re.I), "venda_realizada"),
    (re.compile(r"venda em aberto", re.I), "venda_em_aberto"),
    (re.compile(r"or[cç]amento", re.I), "orcamento"),
    (re.compile(r"obje[cç]", re.I), "objecao"),
    (re.compile(r"cancelad", re.I), "cancelada"),
    (re.compile(r"qualifica", re.I), "em_andamento"),
)


def interpret_by_rules(question: str) -> dict:
    filters: list[dict] = []
    gaps: list[str] = []

    for pattern, value in PRODUCTS:
        if pattern.search(question):
            filters.append({"dimension": "produto", "value": value})
            break

    seller = re.search(r"vendedor\s+([A-Za-zÀ-ú]+)", question, re.I)
    if seller:
        filters.append({"dimension": "vendedor", "value": seller.group(1)})

    for pattern, value in PHASES:
        if pattern.search(question):
            filters.append({"dimension": "fase", "value": value})
            break

    if re.search(r"s[aã]o paulo|rio de janeiro|\bcidade\b|\bpra[cç]a\b|\bestado\b", question, re.I):
        gaps.append("Cidade não é dimensão deste funil. Esse recorte foi ignorado.")

    metric_id = None
    metric_label = None
    if re.search(r"obje[cç]", question, re.I):
        metric_id, metric_label = "objecoes", "objeções"
    elif re.search(r"sentiment", question, re.I):
        metric_id, metric_label = "sentimento", "sentimento do lead"
    elif re.search(r"valor|fatur|oportunidade", question, re.I):
        metric_id, metric_label = "valor_oportunidade", "valor das oportunidades"
    elif re.search(r"venda realizada|vendas realizadas|\bvendas\b", question, re.I):
        metric_id, metric_label = "vendas_realizadas", "vendas realizadas"
    elif any(item["dimension"] == "produto" for item in filters):
        metric_id, metric_label = "valor_oportunidade", "valor das oportunidades"

    recognized = metric_id is not None and (
        len(filters) > 0 or re.search(r"sentiment|obje[cç]|venda", question, re.I) is not None
    )
    if not recognized:
        gaps.insert(
            0,
            "A frase não cita métrica e recorte do funil (produto, fase, vendedor, sentimento ou objeção).",
        )

    future = re.search(r"pr[oó]ximo", question, re.I) is not None
    past = re.search(r"passado|últimos|ultimos|histórico|historico", question, re.I) is not None
    wants_chance = re.search(r"probabil|chance|subir|cair", question, re.I) is not None

    return {
        "question": question,
        "recognized": recognized,
        "metric_id": metric_id if recognized else None,
        "metric_label": metric_label if recognized else None,
        "filters": filters,
        "time_range": "próximo mês" if future else "últimos 30 dias",
        "direction": "cair" if re.search(r"cair", question, re.I) else "subir" if wants_chance or future else "consultar",
        "needs_database": recognized,
        "needs_web": recognized and re.search(r"mercado|not[ií]cia|clima|d[oó]lar|setor|concorr", question, re.I) is not None,
        "needs_simulation": recognized and (wants_chance or future) and not past,
        "answer_form": "probabilidade" if recognized and (wants_chance or future) and not past else "total" if recognized else "lacuna",
        "gaps": gaps,
    }


def _accept_model_plan(question: str, raw: dict) -> dict:
    metric_id = raw.get("metric_id")
    if metric_id not in METRICS:
        raise ValueError(f"A ficha da IA usou métrica fora do catálogo: {metric_id}")
    return {
        "question": question,
        "recognized": True,
        "metric_id": metric_id,
        "metric_label": raw.get("metric_label") or metric_id,
        "filters": raw.get("filters") or [],
        "time_range": raw.get("time_range") or "últimos 30 dias",
        "direction": raw.get("direction") or "consultar",
        "needs_database": True,
        "needs_web": bool(raw.get("needs_web")),
        "needs_simulation": bool(raw.get("needs_simulation")),
        "answer_form": raw.get("answer_form") or ("probabilidade" if raw.get("needs_simulation") else "total"),
        "gaps": list(raw.get("gaps") or []),
    }


def interpret_question(question: str) -> dict:
    model_plan = call_model(question, {"metrics": METRICS})
    if model_plan is None:
        plan = interpret_by_rules(question)
        plan["interpreted_by"] = "regras"
        return plan
    plan = _accept_model_plan(question, model_plan)
    plan["interpreted_by"] = "modelo"
    return plan
