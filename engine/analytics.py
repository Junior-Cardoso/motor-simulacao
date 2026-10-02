"""Uma leitura do grão semanal. Credencial só vem do ambiente, nunca do código."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# Números inventados para o exemplo rodar sem banco. Não são leitura de cliente.
FIXTURE = {
    "Garrafas": [
        ("Semana 1", 40, 4000, 10, 50, 2),
        ("Semana 2", 42, 4200, 11, 52, 1),
        ("Semana 3", 38, 3900, 9, 49, 3),
        ("Semana 4", 45, 4600, 12, 55, 1),
    ],
    "Copos": [
        ("Semana 1", 20, 2000, 6, 48, 1),
        ("Semana 2", 18, 1800, 5, 47, 2),
        ("Semana 3", 22, 2100, 7, 51, 1),
        ("Semana 4", 19, 1900, 6, 49, 2),
    ],
}


def _row(period, product, opportunities, total_value, closed_count, sentiment_score, objection_count, phase, source) -> dict:
    return {
        "period": str(period),
        "product": product,
        "phase": phase,
        "opportunities": int(opportunities or 0),
        "total_value": int(float(total_value or 0)),
        "closed_count": int(closed_count or 0),
        "sentiment_score": int(float(sentiment_score or 0)),
        "objection_count": int(objection_count or 0),
        "source": source,
    }


def _filter(plan: dict, dimension: str) -> str | None:
    return next((item["value"] for item in plan["filters"] if item["dimension"] == dimension), None)


def _fixture(plan: dict) -> list[dict]:
    product = _filter(plan, "produto") or "sem produto"
    phase = _filter(plan, "fase") or "venda_em_aberto"
    chosen = FIXTURE.get(product)
    if chosen is None:
        chosen = [
            ("Semana 1", 10, 1000, 2, 50, 1),
            ("Semana 2", 11, 1100, 2, 51, 1),
            ("Semana 3", 9, 900, 1, 48, 2),
            ("Semana 4", 12, 1200, 3, 54, 1),
        ]
    return [
        _row(period, product, opportunities, total_value, closed_count, sentiment_score, objection_count, phase, "exemplo")
        for period, opportunities, total_value, closed_count, sentiment_score, objection_count in chosen
    ]


def _from_database(plan: dict) -> list[dict]:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_KEY"]
    table = os.environ.get("SUPABASE_FACTS_TABLE", "weekly_facts").strip() or "weekly_facts"
    params = {
        "select": "week,product,phase,seller,opportunities,total_value,closed_count,sentiment_score,objection_count",
        "order": "week.asc",
    }
    product = _filter(plan, "produto")
    phase = _filter(plan, "fase")
    seller = _filter(plan, "vendedor")
    organization = os.environ.get("SUPABASE_ORGANIZATION_ID", "").strip()
    if product:
        params["product"] = f"eq.{product}"
    if phase:
        params["phase"] = f"eq.{phase}"
    if seller:
        params["seller"] = f"eq.{seller}"
    if organization:
        params["organization_id"] = f"eq.{organization}"

    request = urllib.request.Request(
        f"{url}/rest/v1/{urllib.parse.quote(table)}?{urllib.parse.urlencode(params)}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"O banco respondeu {exc.code} na tabela {table}. "
            "Confira a chave no ambiente e se weekly_facts existe. A chave não é gravada no projeto."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Não foi possível alcançar o banco. Confira SUPABASE_URL no ambiente.") from exc

    if not isinstance(payload, list) or not payload:
        raise RuntimeError("A consulta voltou vazia para essa ficha.")

    phase_default = phase or "venda_em_aberto"
    return [
        _row(
            item.get("week"),
            item.get("product") or product or "sem produto",
            item.get("opportunities"),
            item.get("total_value"),
            item.get("closed_count"),
            item.get("sentiment_score"),
            item.get("objection_count"),
            item.get("phase") or phase_default,
            "banco",
        )
        for item in payload
    ]


def query_analytics(plan: dict) -> list[dict]:
    """Uma leitura por pergunta. Sem URL e sem chave, devolve a série de exemplo."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not url or not key:
        return _fixture(plan)
    return _from_database(plan)
