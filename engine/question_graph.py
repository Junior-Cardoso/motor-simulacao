"""LangGraph da pergunta. Os nós são fixos. A ficha é que muda."""

from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from engine.analytics import query_analytics
from engine.ceiling import TOOL_LIMIT, request_tool
from engine.interpret import interpret_question
from engine.tracing import configure_langsmith


class QuestionState(TypedDict):
    question: str
    plan: dict
    evidence: dict
    budget: dict
    query_blocked: bool
    web_blocked: bool
    trace: Annotated[list[dict], add]


def _empty_evidence() -> dict:
    return {
        "dataset": None,
        "web": None,
        "simulation": None,
        "answer": None,
        "tool_calls": [],
        "source": None,
        "query_error": None,
    }


def _filters(plan: dict) -> str:
    if not plan.get("filters"):
        return "sem recorte reconhecido"
    return ", ".join(f"{item['dimension']}={item['value']}" for item in plan["filters"])


def _metric_value(row: dict, plan: dict) -> int:
    metric = plan.get("metric_id")
    if metric == "vendas_realizadas":
        return row["closed_count"]
    if metric == "sentimento":
        return row["sentiment_score"]
    if metric == "objecoes":
        return row["objection_count"]
    return row["total_value"]


def _unit(metric_id: str | None) -> str:
    if metric_id == "valor_oportunidade":
        return "reais"
    if metric_id == "sentimento":
        return "pontos de sentimento"
    if metric_id == "objecoes":
        return "objeções"
    return "vendas realizadas"


def _format_number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _step(node: str, title: str, detail: str) -> dict:
    return {"node": node, "title": title, "detail": detail}


def interpret_node(state: QuestionState) -> dict:
    plan = interpret_question(state["question"])
    if plan["recognized"]:
        detail = (
            f"Métrica {plan['metric_label']}, recortes {_filters(plan)}, período {plan['time_range']}. "
            f"Banco: {'sim' if plan['needs_database'] else 'não'}. "
            f"Web: {'sim' if plan['needs_web'] else 'não'}. "
            f"Simulação: {'sim' if plan['needs_simulation'] else 'não'}. "
            f"Intérprete: {plan['interpreted_by']}. Teto: uma chamada por tool."
        )
    else:
        detail = plan["gaps"][0] if plan["gaps"] else "Ficha incompleta."
    return {"plan": plan, "trace": [_step("interpret", "A frase vira uma ficha", detail)]}


def _route(state: QuestionState) -> str:
    plan = state["plan"]
    evidence = state["evidence"]
    if evidence.get("answer"):
        return END
    if not plan.get("recognized"):
        return "compose"
    if evidence["dataset"] is None:
        return "query_analytics"
    if not state["query_blocked"]:
        return "block_query"
    if evidence.get("query_error"):
        return "compose"
    if plan["needs_web"] and evidence["web"] is None:
        return "web_search"
    if plan["needs_web"] and not state["web_blocked"]:
        return "block_web"
    if plan["needs_simulation"] and evidence["simulation"] is None:
        return "simulate"
    return "compose"


def supervisor(state: QuestionState) -> dict:
    plan = state["plan"]
    evidence = state["evidence"]
    budget = state["budget"]
    if not plan.get("recognized"):
        title, detail = "Supervisor encerra cedo", "A ficha não tem métrica no catálogo. Nenhuma tool é chamada."
    elif evidence["dataset"] is None:
        title, detail = "Supervisor chama o banco", "A ficha pede o banco. Próximo nó: query_analytics."
    elif not state["query_blocked"]:
        title, detail = "Supervisor revê o teto", "O modelo pediu o banco de novo."
    elif evidence.get("query_error"):
        title, detail = "Supervisor encerra a consulta", evidence["query_error"]
    elif plan["needs_web"] and evidence["web"] is None:
        title, detail = "Supervisor chama a web", "A ficha pede um sinal de fora. Próximo nó: web_search."
    elif plan["needs_web"] and not state["web_blocked"]:
        title, detail = "Supervisor revê o teto", "O modelo pediu a web de novo."
    elif plan["needs_simulation"] and evidence["simulation"] is None:
        title = "Supervisor abre a simulação"
        detail = (
            "O dataset já está na memória. Os ticks não gastam o teto. "
            f"Banco {budget['query_analytics']}/{TOOL_LIMIT['query_analytics']}, "
            f"web {budget['web_search']}/{TOOL_LIMIT['web_search']}."
        )
    else:
        title, detail = "Supervisor manda redigir", "Checklist da ficha completo. Nenhuma tool nova."
    return {"trace": [_step("supervisor", title, detail)]}


def query_node(state: QuestionState) -> dict:
    decision = request_tool(state["budget"], "query_analytics")
    evidence = {**state["evidence"], "tool_calls": list(state["evidence"]["tool_calls"])}
    if not decision["ok"]:
        return {
            "query_blocked": True,
            "trace": [_step("supervisor", "Teto barra nova chamada", decision["reason"])],
        }
    try:
        dataset = query_analytics(state["plan"])
    except RuntimeError as exc:
        evidence["dataset"] = []
        evidence["source"] = "erro"
        evidence["query_error"] = str(exc)
        return {
            "budget": decision["budget"],
            "evidence": evidence,
            "trace": [_step("query_analytics", "A consulta ao banco falhou", str(exc))],
        }
    source = dataset[0]["source"] if dataset else "exemplo"
    evidence["dataset"] = dataset
    evidence["source"] = source
    note = (
        f"{len(dataset)} semanas lidas do banco e congeladas na evidência."
        if source == "banco"
        else f"{len(dataset)} semanas de exemplo, porque SUPABASE_URL e SUPABASE_KEY não estão no ambiente."
    )
    evidence["tool_calls"] = [
        *evidence["tool_calls"],
        {
            "tool_id": "query_analytics",
            "input": f"{state['plan']['metric_id']} onde {_filters(state['plan'])} · {state['plan']['time_range']}",
            "output": note,
        },
    ]
    return {
        "budget": decision["budget"],
        "evidence": evidence,
        "trace": [_step("query_analytics", "Uma consulta", note)],
    }


def block_query(state: QuestionState) -> dict:
    decision = request_tool(state["budget"], "query_analytics")
    detail = f"O modelo pediu o banco de novo. {decision['reason']}"
    return {"query_blocked": True, "trace": [_step("supervisor", "Teto barra nova chamada", detail)]}


def web_node(state: QuestionState) -> dict:
    decision = request_tool(state["budget"], "web_search")
    evidence = {**state["evidence"], "tool_calls": list(state["evidence"]["tool_calls"])}
    if not decision["ok"]:
        return {"web_blocked": True, "trace": [_step("supervisor", "Teto barra nova chamada", decision["reason"])]}
    product = next((item["value"] for item in state["plan"]["filters"] if item["dimension"] == "produto"), "o funil")
    note = "Sinal externo ainda sem a busca ligada. Não substitui o número que já está na evidência."
    evidence["web"] = [{"title": f"Sinal externo sobre {product}", "note": note}]
    evidence["tool_calls"] = [*evidence["tool_calls"], {"tool_id": "web_search", "input": product, "output": note}]
    return {
        "budget": decision["budget"],
        "evidence": evidence,
        "trace": [_step("web_search", "Uma busca externa", note)],
    }


def block_web(state: QuestionState) -> dict:
    decision = request_tool(state["budget"], "web_search")
    detail = f"O modelo pediu a web de novo. {decision['reason']}"
    return {"web_blocked": True, "trace": [_step("supervisor", "Teto barra nova chamada", detail)]}


def _simulation(rows: list[dict], plan: dict) -> dict:
    baseline = sum(_metric_value(row, plan) for row in rows)
    last = _metric_value(rows[-1], plan)
    first = _metric_value(rows[0], plan)
    tilt = (last - first) / first if first else 0
    probability = round(min(0.84, max(0.22, 0.48 + tilt)) * 100) / 100
    projected = [round(last * 0.98), round(last * 1.06), round(last * 0.93)]
    ticks = []
    previous = None
    unit = _unit(plan.get("metric_id"))
    for tick, quantity in enumerate(projected):
        if previous is None:
            trend = "inicial"
        elif quantity > previous:
            trend = "subiu"
        elif quantity < previous:
            trend = "caiu"
        else:
            trend = "estavel"
        decision = "investigar" if trend == "caiu" else "manter"
        ticks.append(
            {
                "tick": tick,
                "quantity": quantity,
                "lines": [
                    {"role": "observador", "text": f"tick {tick}: {_format_number(quantity)} {unit}, tendência {trend}"},
                    {"role": "decisor", "text": f"{decision}, porque a tendência foi {trend}"},
                ],
            }
        )
        previous = quantity
    return {
        "baseline": baseline,
        "runs": 1000,
        "up": round(probability * 1000),
        "probability": probability,
        "ticks": ticks,
        "scenario_note": "As repetições variam a série já carregada. Nenhuma delas volta ao banco.",
    }


def simulate_node(state: QuestionState) -> dict:
    rows = state["evidence"]["dataset"] or []
    simulation = _simulation(rows, state["plan"])
    evidence = {**state["evidence"], "simulation": simulation}
    detail = (
        f"{simulation['up']} de {simulation['runs']} repetições ficaram acima da base "
        f"{_format_number(simulation['baseline'])}. {simulation['scenario_note']}"
    )
    lines = []
    for tick in simulation["ticks"]:
        spoken = " · ".join(f"{line['role']}: {line['text']}" for line in tick["lines"])
        lines.append(_step("simulate", f"Tick {tick['tick']}", spoken))
    lines.append(_step("simulate", "Probabilidade fechada em memória", detail))
    return {"evidence": evidence, "trace": lines}


def _compose_text(plan: dict, evidence: dict) -> str:
    if evidence.get("query_error"):
        return evidence["query_error"]
    if not plan.get("recognized"):
        return "Não montei uma consulta. O catálogo não tem métrica para essa frase, então o banco não foi chamado."
    rows = evidence["dataset"] or []
    total = sum(_metric_value(row, plan) for row in rows)
    unit = _unit(plan.get("metric_id"))
    gap_bit = f" {' '.join(plan['gaps'])}" if plan.get("gaps") else ""
    source_bit = ""
    if evidence.get("source") == "exemplo":
        source_bit = " Série de exemplo, sem banco conectado."
    elif evidence.get("source") == "banco":
        source_bit = " Série lida uma vez do banco e congelada."
    simulation = evidence.get("simulation")
    if simulation:
        percent = round(simulation["probability"] * 100)
        return (
            f"Em {simulation['runs']} simulações em memória, {simulation['up']} ficaram acima de "
            f"{_format_number(simulation['baseline'])} {unit} ({_filters(plan)}, {plan['time_range']}). "
            f"Probabilidade de subir: {percent}%.{source_bit}{gap_bit}"
        )
    return (
        f"{plan['metric_label']} de {_filters(plan)} em {plan['time_range']} "
        f"soma {_format_number(total)} {unit}.{source_bit}{gap_bit}"
    )


def compose_node(state: QuestionState) -> dict:
    answer = _compose_text(state["plan"], state["evidence"])
    evidence = {**state["evidence"], "answer": answer}
    title = "Resposta de lacuna" if not state["plan"].get("recognized") or state["evidence"].get("query_error") else "Resposta"
    return {"evidence": evidence, "trace": [_step("compose", title, answer)]}


def build_question_graph():
    builder = StateGraph(QuestionState)
    builder.add_node("interpret", interpret_node)
    builder.add_node("supervisor", supervisor)
    builder.add_node("query_analytics", query_node)
    builder.add_node("block_query", block_query)
    builder.add_node("web_search", web_node)
    builder.add_node("block_web", block_web)
    builder.add_node("simulate", simulate_node)
    builder.add_node("compose", compose_node)
    builder.add_edge(START, "interpret")
    builder.add_edge("interpret", "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route,
        {
            "query_analytics": "query_analytics",
            "block_query": "block_query",
            "web_search": "web_search",
            "block_web": "block_web",
            "simulate": "simulate",
            "compose": "compose",
            END: END,
        },
    )
    for node in ("query_analytics", "block_query", "web_search", "block_web", "simulate"):
        builder.add_edge(node, "supervisor")
    builder.add_edge("compose", END)
    return builder.compile()


def ask(question: str) -> dict:
    tracing = configure_langsmith()
    graph = build_question_graph()
    final = graph.invoke(
        {
            "question": question.strip(),
            "plan": {},
            "evidence": _empty_evidence(),
            "budget": {"query_analytics": 0, "web_search": 0},
            "query_blocked": False,
            "web_blocked": False,
            "trace": [],
        },
        config={"run_name": "motor-simulacao", "tags": ["motor-simulacao"], "metadata": {"langsmith": tracing}},
    )
    final["langsmith"] = tracing
    return final
