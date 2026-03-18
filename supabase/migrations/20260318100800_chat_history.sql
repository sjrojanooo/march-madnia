create table public.chat_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  expert_id text not null,
  messages jsonb not null default '[]'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (user_id, expert_id)
);

alter table public.chat_history enable row level security;

create policy "Users can read own chat history"
  on public.chat_history for select
  using (auth.uid() = user_id);

create policy "Users can insert own chat history"
  on public.chat_history for insert
  with check (auth.uid() = user_id);

create policy "Users can update own chat history"
  on public.chat_history for update
  using (auth.uid() = user_id);

create index idx_chat_history_user on public.chat_history (user_id);
