-- Minimal seed: populated by scripts/seed_supabase.py

insert into public.expert_picks (expert_id, expert_name, source, season, champion)
values
  ('jay_bilas', 'Jay Bilas', 'ESPN', 2026, 'duke'),
  ('seth_davis', 'Seth Davis', 'CBS Sports', 2026, 'auburn')
on conflict (expert_id, season) do nothing;
