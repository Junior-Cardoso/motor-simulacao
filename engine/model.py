"""Único ponto da chamada de IA.

O grafo, o teto, a consulta e a simulação não passam por aqui.
Quando a API do ChatGPT entrar, `call_model` devolve a ficha.
Enquanto devolver None, as regras do catálogo preenchem a ficha.
"""


def call_model(question: str, catalog: dict) -> dict | None:
    """Devolva a ficha, ou None para usar as regras.

    Campos: metric_id, metric_label, filters [{dimension, value}],
    time_range, direction, needs_web, needs_simulation, gaps.
    metric_id tem de existir em catalog["metrics"].
    """
    del question, catalog
    return None
