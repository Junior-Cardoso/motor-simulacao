# Motor de simulação

Uma pergunta entra, vira uma ficha e segue um grafo fixo. O banco é lido uma vez. O mês seguinte é calculado em memória, em cima dessa série. A segunda leitura é barrada.

Não há dado de cliente neste repositório. Não há arquivo `.env`. A chave do banco, se você tiver uma, fica só na sua máquina.

## O que cada peça faz

| Peça | Onde | Função |
| --- | --- | --- |
| Ficha | `engine/interpret.py` | Traduz a frase em métrica, recorte e período. |
| Catálogo | `engine/catalog.py` | Lista o que a ficha pode pedir. Cidade não entra. |
| Chamada de IA | `engine/model.py` | Único lugar da API do ChatGPT. Hoje devolve vazio e as regras preenchem a ficha. |
| Banco | `engine/analytics.py` | Uma consulta. Sem chave, usa a série de exemplo. |
| Teto | `engine/ceiling.py` | Cada ferramenta dispara no máximo uma vez. |
| Simulação | `engine/question_graph.py` | Mil repetições da série já carregada. Não volta ao banco. |
| Rastro | `engine/tracing.py` | Envia os passos ao LangSmith só se existir `LANGSMITH_API_KEY`. |

O grafo é: interpretar, supervisionar, consultar, barrar a segunda consulta, simular, redigir.

## Rodar sem banco

```bash
pip install -r requirements.txt
python ask.py "Probabilidade das vendas de copos subirem no próximo mês"
```

A resposta diz que a série é de exemplo.

## Ligar o seu banco

1. Crie a tabela vazia com `schema.sql`.
2. Copie `.env.example` para `.env` e preencha `SUPABASE_URL` e `SUPABASE_KEY` na sua máquina.
3. Não commite o `.env`. Ele está no `.gitignore`.

O código lê essas variáveis na hora da consulta e não grava a chave em arquivo do projeto. A leitura pede a tabela `weekly_facts`, no grão organização + vendedor + produto + semana + fase, filtrando o que a ficha reconheceu.

## Como saber se a simulação mente

Esconda o último período real, rode a pergunta, e só depois compare com o que aconteceu. Se o número previsto não cabe no que aqueles mesmos casos fizeram, a simulação mente. Se o texto do modelo inventa a probabilidade, ela também mente: aqui o modelo só pode preencher a ficha. O número sai da série congelada.
