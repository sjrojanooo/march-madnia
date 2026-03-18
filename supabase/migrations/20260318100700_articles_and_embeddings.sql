create table public.articles (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  url text unique not null,
  title text,
  content text,
  published_at timestamptz,
  scraped_at timestamptz default now(),
  metadata jsonb default '{}'::jsonb
);

create table public.article_embeddings (
  id uuid primary key default gen_random_uuid(),
  article_id uuid not null references public.articles on delete cascade,
  chunk_index int not null,
  content_chunk text not null,
  embedding vector(1536),
  metadata jsonb default '{}'::jsonb,
  unique (article_id, chunk_index)
);

create index idx_article_embeddings_hnsw
  on public.article_embeddings
  using hnsw (embedding vector_cosine_ops);

alter table public.articles enable row level security;
alter table public.article_embeddings enable row level security;
create policy "Articles are publicly readable" on public.articles for select using (true);
create policy "Embeddings are publicly readable" on public.article_embeddings for select using (true);
