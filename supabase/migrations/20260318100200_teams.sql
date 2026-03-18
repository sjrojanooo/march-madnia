create table public.teams (
  slug text not null,
  display_name text not null,
  conference text,
  season int not null,
  seed int,
  srs real,
  off_rtg real,
  pace real,
  conf_win_pct real,
  rotation_depth real,
  created_at timestamptz default now(),
  primary key (slug, season)
);

alter table public.teams enable row level security;
create policy "Teams are publicly readable" on public.teams for select using (true);
