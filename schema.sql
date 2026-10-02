-- Tabela vazia que o motor sabe ler.
-- Não há linhas aqui. Os dados ficam no seu banco, não neste repositório.

create table if not exists public.weekly_facts (
  id bigint generated always as identity primary key,
  organization_id uuid,
  seller text,
  product text,
  phase text,
  week date not null,
  opportunities integer not null default 0,
  total_value numeric not null default 0,
  closed_count integer not null default 0,
  sentiment_score numeric not null default 0,
  objection_count integer not null default 0
);
