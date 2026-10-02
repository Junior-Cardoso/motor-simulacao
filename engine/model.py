"""Único ponto da chamada de IA.

Sem OPENAI_API_KEY, devolve None e as regras preenchem a ficha.
Com a chave no ambiente ou num .env local, pede a ficha ao modelo.
A chave não entra no código. A probabilidade continua saindo da série, não do texto.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_local_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        name, value = text.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def call_model(question: str, catalog: dict) -> dict | None:
    """Devolve a ficha do modelo, ou None quando não há chave.

    Campos: metric_id, metric_label, filters [{dimension, value}],
    time_range, direction, needs_web, needs_simulation, gaps.
    metric_id tem de existir em catalog["metrics"].
    """
    _load_local_env()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None

    metrics = catalog.get("metrics") or {}
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    instructions = (
        "Traduza a pergunta numa ficha JSON. Não calcule probabilidade e não invente número. "
        f"metric_id só pode ser um destes: {', '.join(metrics)}. "
        "filters só pode usar dimension produto, vendedor ou fase. "
        "Cidade, estado e praça não são dimensão: registre isso em gaps e não crie esse filtro. "
        "needs_simulation é true se a pergunta pede chance, subir, cair ou o próximo período. "
        "needs_web é true só se pede mercado, notícia, clima, dólar, setor ou concorrente. "
        "Responda só o JSON com metric_id, metric_label, filters, time_range, direction, "
        "needs_web, needs_simulation, gaps."
    )
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": question},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"A OpenAI respondeu {exc.code}. Confira OPENAI_API_KEY no .env. A chave não fica no projeto."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Não foi possível alcançar a OpenAI.") from exc

    content = body["choices"][0]["message"]["content"]
    plan = json.loads(content)
    if not isinstance(plan, dict):
        raise RuntimeError("A OpenAI não devolveu a ficha em JSON.")
    return plan


def explain_result(sheet: dict) -> str | None:
    """Explica a série já calculada. Não devolve outro número.

    Sem chave, devolve None e o motor usa o texto factual da própria série.
    """
    _load_local_env()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key or not sheet:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    instructions = (
        "Explique em português, em até quatro frases, o que está por trás do número. "
        "Use somente o JSON recebido. A probabilidade e a base estão fechadas: repita esses números e não os troque. "
        "Se a causa da semana não estiver no JSON, diga que a série mostra o tamanho da oscilação e não a causa. "
        "Não invente campanha, cliente, vendedor nem notícia."
    )
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(sheet, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"A OpenAI respondeu {exc.code} ao explicar a série. A chave não fica no projeto."
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Não foi possível alcançar a OpenAI para explicar a série.") from exc
    return str(body["choices"][0]["message"]["content"]).strip()
