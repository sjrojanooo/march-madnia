create table public.bracket_ratings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  bracket_id uuid not null references public.user_brackets on delete cascade,
  expert_id text not null,
  rating int not null check (rating between 1 and 10),
  assessment text,
  suggestions jsonb,
  created_at timestamptz default now()
);

alter table public.bracket_ratings enable row level security;

create policy "Users can read own ratings"
  on public.bracket_ratings for select
  using ((select auth.uid()) = user_id);

create policy "Users can insert own ratings"
  on public.bracket_ratings for insert
  with check ((select auth.uid()) = user_id);

create policy "Users can update own ratings"
  on public.bracket_ratings for update
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete own ratings"
  on public.bracket_ratings for delete
  using ((select auth.uid()) = user_id);

create index idx_bracket_ratings_bracket on public.bracket_ratings (bracket_id);
