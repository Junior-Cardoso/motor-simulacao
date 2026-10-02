TOOL_LIMIT = {
    "query_analytics": 1,
    "web_search": 1,
}


def request_tool(budget: dict, tool_id: str) -> dict:
    limit = TOOL_LIMIT[tool_id]
    used = budget[tool_id]
    if used >= limit:
        return {
            "ok": False,
            "budget": budget,
            "reason": (
                f"{tool_id} está em {used}/{limit}. "
                "Outra chamada fica barrada e a evidência já coletada segue adiante."
            ),
        }
    return {
        "ok": True,
        "budget": {**budget, tool_id: used + 1},
        "reason": "",
    }
