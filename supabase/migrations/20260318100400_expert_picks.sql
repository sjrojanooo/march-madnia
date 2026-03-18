create table public.expert_picks (
  id uuid primary key default gen_random_uuid(),
  expert_id text not null,
  expert_name text not null,
  source text,
  season int not null default 2026,
  champion text,
  final_four text[],
  elite_8 text[],
  picks jsonb,
  created_at timestamptz default now(),
  unique (expert_id, season)
);

alter table public.expert_picks enable row level security;
create policy "Expert picks are publicly readable" on public.expert_picks for select using (true);
