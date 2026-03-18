-- Minimal seed: populated by scripts/seed_supabase.py
-- This file exists so `supabase db reset` has something to run

insert into public.teams (slug, display_name, conference, season, seed, srs)
values
  ('duke', 'Duke', 'ACC', 2026, 1, 25.5),
  ('auburn', 'Auburn', 'SEC', 2026, 1, 24.8),
  ('florida', 'Florida', 'SEC', 2026, 1, 23.2),
  ('houston', 'Houston', 'Big 12', 2026, 1, 22.9)
on conflict (slug, season) do nothing;
