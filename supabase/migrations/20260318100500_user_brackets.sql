create table public.user_brackets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  season int not null default 2026,
  picks jsonb not null default '{}'::jsonb,
  name text not null default 'My Bracket',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table public.user_brackets enable row level security;

create policy "Users can read own brackets"
  on public.user_brackets for select
  using ((select auth.uid()) = user_id);

create policy "Users can insert own brackets"
  on public.user_brackets for insert
  with check ((select auth.uid()) = user_id);

create policy "Users can update own brackets"
  on public.user_brackets for update
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete own brackets"
  on public.user_brackets for delete
  using ((select auth.uid()) = user_id);

create index idx_user_brackets_user_id on public.user_brackets (user_id);
