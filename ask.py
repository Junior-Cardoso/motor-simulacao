"""Roda uma pergunta no LangGraph.

Sem SUPABASE_URL e SUPABASE_KEY, a série é de exemplo.
Com as duas variáveis no ambiente, a mesma ficha lê weekly_facts.
"""

import json
import sys

from engine.question_graph import ask


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or (
        "Probabilidade das vendas de copos subirem no próximo mês"
    )
    result = ask(question)
    print(result["evidence"]["answer"])
    print("---")
    for step in result["trace"]:
        print(f"[{step['node']}] {step['title']}")
        print(f"  {step['detail']}")
    print("---")
    print("fonte:", result["evidence"].get("source"))
    print("langsmith:", result["langsmith"])
    print("ficha:", json.dumps(result["plan"], ensure_ascii=False))


if __name__ == "__main__":
    main()
