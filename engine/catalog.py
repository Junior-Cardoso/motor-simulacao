"""O que a ficha pode preencher. Fora desta lista, a pergunta não vira consulta."""

METRICS = {
    "valor_oportunidade": "soma semanal do valor em aberto",
    "vendas_realizadas": "contagem semanal de vendas fechadas",
    "sentimento": "leitura semanal de sentimento",
    "objecoes": "contagem semanal de objeções",
}

DIMENSIONS = ("organizacao", "vendedor", "produto", "fase", "periodo")

PHASES = (
    "em_andamento",
    "orcamento",
    "venda_em_aberto",
    "venda_realizada",
    "objecao",
    "cancelada",
    "fora_de_contexto",
)

GRAIN = "organização + vendedor + produto + semana + fase"
