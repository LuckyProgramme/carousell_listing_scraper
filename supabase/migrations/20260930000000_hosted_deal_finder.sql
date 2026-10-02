-- Canonical Deal Finder storage, access rules, and three-day retention.
-- This migration is intentionally unapplied; review it before pushing to Supabase.

create extension if not exists pg_cron with schema pg_catalog;
create schema if not exists deal_finder_private;
revoke all on schema deal_finder_private from public, anon, authenticated;

create table public.targets (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  item_name text not null check (char_length(btrim(item_name)) between 1 and 200),
  category text not null default '' check (char_length(category) <= 120),
  search_mode text not null default 'Category'
    check (search_mode in ('Category', 'Item Name')),
  deal_price numeric(12,2) not null check (deal_price > 0),
  retail_price numeric(12,2) check (retail_price is null or retail_price > 0),
  downsizing_keywords text[] not null default '{}',
  freebie_keywords text[] not null default '{}',
  notes text not null default '' check (char_length(notes) <= 2000),
  target_type text not null default 'Hardware'
    check (target_type in ('Hardware', 'Game')),
  allow_bundle_check boolean not null default false,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint category_required_for_category_mode
    check (search_mode <> 'Category' or char_length(btrim(category)) > 0),
  constraint targets_owner_item_name_unique unique (owner_id, item_name)
);

create table public.scan_runs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued', 'scanning', 'evaluating', 'saving', 'completed', 'failed')),
  listings_count integer not null default 0 check (listings_count >= 0),
  candidates_count integer not null default 0 check (candidates_count >= 0),
  deals_count integer not null default 0 check (deals_count >= 0),
  safe_error text check (safe_error is null or char_length(safe_error) <= 500),
  target_snapshot jsonb not null default '[]'::jsonb
    check (jsonb_typeof(target_snapshot) = 'array'),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now()
);

create table public.listings (
  id uuid primary key default gen_random_uuid(),
  scan_run_id uuid not null references public.scan_runs(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  source_listing_id text not null check (char_length(btrim(source_listing_id)) between 1 and 300),
  title text not null check (char_length(btrim(title)) between 1 and 500),
  price numeric(12,2) check (price is null or price >= 0),
  condition text not null default '' check (char_length(condition) <= 120),
  description text not null default '',
  link text not null default '' check (char_length(link) <= 2000),
  seller text not null default '' check (char_length(seller) <= 300),
  category text not null default '' check (char_length(category) <= 200),
  thumbnail_url text check (thumbnail_url is null or char_length(thumbnail_url) <= 3000),
  seller_rating numeric(4,2) check (seller_rating is null or seller_rating between 0 and 5),
  seller_rating_count integer check (seller_rating_count is null or seller_rating_count >= 0),
  like_count integer check (like_count is null or like_count >= 0),
  location text check (location is null or char_length(location) <= 300),
  listing_timestamp text check (listing_timestamp is null or char_length(listing_timestamp) <= 200),
  price_flag text not null default 'normal' check (char_length(price_flag) <= 80),
  created_at timestamptz not null default now(),
  constraint listings_scan_source_unique unique (scan_run_id, source_listing_id)
);

create table public.evaluations (
  id uuid primary key default gen_random_uuid(),
  scan_run_id uuid not null references public.scan_runs(id) on delete cascade,
  listing_id uuid not null references public.listings(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  target_id uuid references public.targets(id) on delete set null,
  target_snapshot_id uuid not null,
  accepted boolean not null default false,
  matched_item text check (matched_item is null or char_length(matched_item) <= 200),
  target_snapshot jsonb not null default '{}'::jsonb
    check (jsonb_typeof(target_snapshot) = 'object'),
  audit_source text check (audit_source is null or audit_source in ('gemini', 'local_fallback')),
  confidence integer check (confidence is null or confidence between 0 and 100),
  specs_matched boolean,
  local_match_score numeric(5,2)
    check (local_match_score is null or local_match_score between 0 and 100),
  issues text[] not null default '{}',
  freebies text[] not null default '{}',
  final_condition text check (final_condition is null or char_length(final_condition) <= 120),
  condition_overridden boolean not null default false,
  deal_price numeric(12,2) check (deal_price is null or deal_price > 0),
  retail_price numeric(12,2) check (retail_price is null or retail_price > 0),
  evaluated_price numeric(12,2) check (evaluated_price is null or evaluated_price > 0),
  savings numeric(12,2),
  acceptance_reason text check (acceptance_reason is null or char_length(acceptance_reason) <= 2000),
  is_bundle boolean not null default false,
  individual_price numeric(12,2) check (individual_price is null or individual_price > 0),
  price_evidence text check (price_evidence is null or char_length(price_evidence) <= 800),
  created_at timestamptz not null default now(),
  constraint evaluations_listing_snapshot_target_unique
    unique (listing_id, target_snapshot_id)
);

-- Keep denormalized owner/scan columns consistent even for privileged server writes.
alter table public.scan_runs
  add constraint scan_runs_id_owner_unique unique (id, owner_id);
alter table public.listings
  add constraint listings_id_scan_owner_unique unique (id, scan_run_id, owner_id),
  add constraint listings_scan_owner_fk foreign key (scan_run_id, owner_id)
    references public.scan_runs(id, owner_id) on delete cascade;
alter table public.evaluations
  add constraint evaluations_scan_owner_fk foreign key (scan_run_id, owner_id)
    references public.scan_runs(id, owner_id) on delete cascade,
  add constraint evaluations_listing_scan_owner_fk
    foreign key (listing_id, scan_run_id, owner_id)
    references public.listings(id, scan_run_id, owner_id) on delete cascade;

create unique index scan_runs_one_active_per_owner_idx
  on public.scan_runs (owner_id)
  where status in ('queued', 'scanning', 'evaluating', 'saving');
create index targets_owner_id_idx on public.targets (owner_id);
create index scan_runs_owner_created_idx on public.scan_runs (owner_id, created_at desc);
create index listings_owner_created_idx on public.listings (owner_id, created_at desc);
create index listings_scan_run_id_idx on public.listings (scan_run_id);
create index evaluations_owner_created_idx on public.evaluations (owner_id, created_at desc);
create index evaluations_scan_run_id_idx on public.evaluations (scan_run_id);
create index evaluations_listing_id_idx on public.evaluations (listing_id);
create index evaluations_target_id_idx on public.evaluations (target_id);
create index evaluations_accepted_idx on public.evaluations (owner_id, accepted, created_at desc);

create function deal_finder_private.touch_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke execute on function deal_finder_private.touch_updated_at() from public, anon, authenticated;

create trigger targets_touch_updated_at
before update on public.targets
for each row execute function deal_finder_private.touch_updated_at();

create trigger scan_runs_touch_updated_at
before update on public.scan_runs
for each row execute function deal_finder_private.touch_updated_at();

alter table public.targets enable row level security;
alter table public.scan_runs enable row level security;
alter table public.listings enable row level security;
alter table public.evaluations enable row level security;

revoke all on table public.targets, public.scan_runs, public.listings, public.evaluations
  from anon, authenticated;
grant select, insert, update, delete on table public.targets to authenticated;
grant select on table public.scan_runs, public.listings, public.evaluations to authenticated;
grant all on table public.targets, public.scan_runs, public.listings, public.evaluations to service_role;

create policy targets_select_own on public.targets
for select to authenticated
using ((select auth.uid()) = owner_id);
create policy targets_insert_own on public.targets
for insert to authenticated
with check ((select auth.uid()) = owner_id);
create policy targets_update_own on public.targets
for update to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);
create policy targets_delete_own on public.targets
for delete to authenticated
using ((select auth.uid()) = owner_id);

create policy scan_runs_select_own on public.scan_runs
for select to authenticated
using ((select auth.uid()) = owner_id);
create policy listings_select_own on public.listings
for select to authenticated
using ((select auth.uid()) = owner_id);
create policy evaluations_select_own on public.evaluations
for select to authenticated
using ((select auth.uid()) = owner_id);

create function deal_finder_private.cleanup_expired_scans()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  deleted_count bigint;
begin
  delete from public.scan_runs
  where created_at < now() - interval '3 days';
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke execute on function deal_finder_private.cleanup_expired_scans()
  from public, anon, authenticated;

select cron.schedule(
  'deal-finder-retention-cleanup',
  '17 3 * * *',
  'select deal_finder_private.cleanup_expired_scans();'
);
