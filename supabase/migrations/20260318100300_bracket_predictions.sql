create table public.bracket_predictions (
  id uuid primary key default gen_random_uuid(),
  season int not null,
  game_slot text not null,
  winner text not null,
  win_probability real not null,
  model_version text not null default 'ensemble_with2025',
  created_at timestamptz default now(),
  unique (season, game_slot, model_version)
);

alter table public.bracket_predictions enable row level security;
create policy "Predictions are publicly readable" on public.bracket_predictions for select using (true);
