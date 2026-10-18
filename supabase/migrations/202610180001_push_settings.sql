-- Voer eerst docs/pushmeldingen.md en supabase/preflight.sql uit.
-- Transactioneel: bestaande instellingen worden niet overschreven.
begin;
create table if not exists public.lcp_push_preferences (
 id boolean primary key default true check(id),
 title text not null default 'LCP – Oproep',
 fallback_body text not null default 'Er is op de oproepknop gedrukt.',
 icon_url text,
 updated_at timestamptz not null default now()
);
alter table public.lcp_push_preferences add column if not exists fallback_body text not null default 'Er is op de oproepknop gedrukt.';
alter table public.lcp_push_preferences add column if not exists app_name text not null default 'LCP';
-- De bestaande installatie gebruikt één algemene voorkeurenrij. Bij een ander
-- model moet eerst de bestaande servercode worden onderzocht, niet geconverteerd.
do $$
begin
 if (select count(*) from public.lcp_push_preferences)>1 then
  raise exception 'Meerdere voorkeurenrijen aangetroffen. Onderzoek het bestaande gegevensmodel vóór activering.';
 end if;
 if not exists(select 1 from public.lcp_push_preferences) then
  -- Gebruikt uitsluitend bestaande standaardwaarden voor id/overige kolommen.
  insert into public.lcp_push_preferences(title) values('LCP – Oproep');
 end if;
end $$;
update public.lcp_push_preferences set title='LCP – Oproep',fallback_body='Er is op de oproepknop gedrukt.',updated_at=clock_timestamp()
where title='LCP oproep' and fallback_body='Er is een nieuwe oproep bij het LCP.';
create unique index if not exists lcp_push_preferences_singleton_v2 on public.lcp_push_preferences((true));

create or replace function public.lcp_push_is_member() returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.lcp_members where user_id=(select auth.uid()))
$$;
create or replace function public.lcp_push_is_admin() returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.lcp_members where user_id=(select auth.uid()) and role='admin')
$$;
revoke all on function public.lcp_push_is_member(),public.lcp_push_is_admin() from public;
grant execute on function public.lcp_push_is_member(),public.lcp_push_is_admin() to anon,authenticated;

alter table public.lcp_push_preferences enable row level security;
-- Restrictieve regels sluiten ook mogelijk te brede bestaande policies in.
-- Bestaande policies blijven bestaan; service_role voor de afzender blijft werken.
drop policy if exists lcp_push_member_guard_v2 on public.lcp_push_preferences;
create policy lcp_push_member_guard_v2 on public.lcp_push_preferences as restrictive for select to anon,authenticated using(public.lcp_push_is_member());
drop policy if exists lcp_push_admin_guard_v2 on public.lcp_push_preferences;
create policy lcp_push_admin_guard_v2 on public.lcp_push_preferences as restrictive for all to anon,authenticated using(public.lcp_push_is_member()) with check(public.lcp_push_is_admin());
drop policy if exists lcp_push_update_guard_v2 on public.lcp_push_preferences;
create policy lcp_push_update_guard_v2 on public.lcp_push_preferences as restrictive for update to anon,authenticated using(public.lcp_push_is_admin()) with check(public.lcp_push_is_admin());
drop policy if exists lcp_push_delete_guard_v2 on public.lcp_push_preferences;
create policy lcp_push_delete_guard_v2 on public.lcp_push_preferences as restrictive for delete to anon,authenticated using(public.lcp_push_is_admin());

create or replace function public.lcp_get_push_settings() returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare result jsonb;
begin
 if not public.lcp_push_is_member() then raise exception 'Geen toegang.' using errcode='42501'; end if;
 select jsonb_build_object('title',title,'icon_url',icon_url,'default_message',fallback_body,'app_name',app_name,'updated_at',updated_at) into result from public.lcp_push_preferences;
 return result;
end $$;
create or replace function public.lcp_save_push_settings(p_settings jsonb,p_expected_updated_at timestamptz) returns jsonb
language plpgsql security definer set search_path='' as $$
declare current_stamp timestamptz; logo text;
begin
 if not public.lcp_push_is_admin() then raise exception 'Alleen beheerders mogen dit aanpassen.' using errcode='42501'; end if;
 if jsonb_typeof(p_settings) is distinct from 'object' then raise exception 'Ongeldige instellingen.' using errcode='22023'; end if;
 if jsonb_typeof(p_settings->'title') is distinct from 'string' or char_length(btrim(p_settings->>'title')) not between 1 and 100
 or jsonb_typeof(p_settings->'default_message') is distinct from 'string' or char_length(btrim(p_settings->>'default_message')) not between 1 and 240
 or jsonb_typeof(p_settings->'app_name') is distinct from 'string' or char_length(btrim(p_settings->>'app_name')) not between 1 and 24 then
  raise exception 'Vul een geldige titel, standaardtekst en appnaam in.' using errcode='22023';
 end if;
 logo:=p_settings->>'icon_url';
 if logo is null or (logo not in('./icon-192.png','./icon-512.png') and logo !~ '^https://jrlcofhpxvnlqzirjdbd[.]supabase[.]co/storage/v1/object/public/lcp-branding/([A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+[.]png$') then
  raise exception 'Ongeldig PNG-logo.' using errcode='22023';
 end if;
 select updated_at into current_stamp from public.lcp_push_preferences where id=true for update;
 if current_stamp is distinct from p_expected_updated_at then raise exception 'De instellingen zijn intussen gewijzigd.' using errcode='40001'; end if;
 update public.lcp_push_preferences set title=btrim(p_settings->>'title'),fallback_body=btrim(p_settings->>'default_message'),app_name=btrim(p_settings->>'app_name'),icon_url=logo,updated_at=clock_timestamp() where id=true;
 return public.lcp_get_push_settings();
end $$;
revoke all on function public.lcp_get_push_settings(),public.lcp_save_push_settings(jsonb,timestamptz) from public;
grant execute on function public.lcp_get_push_settings(),public.lcp_save_push_settings(jsonb,timestamptz) to authenticated;

-- Hergebruik bestaande opslag. Maak de bucket alleen als hij echt ontbreekt.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('lcp-branding','lcp-branding',true,2097152,array['image/png']) on conflict(id) do nothing;
do $$ begin
 if not exists(select 1 from storage.buckets where id='lcp-branding' and public) then
  raise exception 'De bestaande lcp-branding-bucket is privé. Controleer bestaande bestanden voordat logo-opslag openbaar wordt gemaakt.';
 end if;
end $$;
drop policy if exists lcp_logo_read_v2 on storage.objects;
create policy lcp_logo_read_v2 on storage.objects for select to anon,authenticated using(bucket_id='lcp-branding');
drop policy if exists lcp_logo_admin_insert_v2 on storage.objects;
create policy lcp_logo_admin_insert_v2 on storage.objects for insert to authenticated with check(bucket_id='lcp-branding' and public.lcp_push_is_admin() and split_part(name,'/',1)=(select auth.uid())::text and name ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}[.]png$');
drop policy if exists lcp_logo_admin_delete_v2 on storage.objects;
create policy lcp_logo_admin_delete_v2 on storage.objects for delete to authenticated using(bucket_id='lcp-branding' and public.lcp_push_is_admin() and split_part(name,'/',1)=(select auth.uid())::text);
-- Extra restricties laten regels voor andere buckets ongemoeid.
drop policy if exists lcp_logo_insert_guard_v2 on storage.objects;
create policy lcp_logo_insert_guard_v2 on storage.objects as restrictive for insert to anon,authenticated with check(bucket_id<>'lcp-branding' or (public.lcp_push_is_admin() and split_part(name,'/',1)=(select auth.uid())::text and name ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}[.]png$' and metadata->>'mimetype'='image/png'));
drop policy if exists lcp_logo_update_guard_v2 on storage.objects;
create policy lcp_logo_update_guard_v2 on storage.objects as restrictive for update to anon,authenticated using(bucket_id<>'lcp-branding') with check(bucket_id<>'lcp-branding');
drop policy if exists lcp_logo_delete_guard_v2 on storage.objects;
create policy lcp_logo_delete_guard_v2 on storage.objects as restrictive for delete to anon,authenticated using(bucket_id<>'lcp-branding' or (public.lcp_push_is_admin() and split_part(name,'/',1)=(select auth.uid())::text));

create table if not exists public.lcp_push_test_limits(user_id uuid primary key,last_sent_at timestamptz not null default now());
alter table public.lcp_push_test_limits enable row level security;
revoke all on public.lcp_push_test_limits from anon,authenticated;
create or replace function public.lcp_claim_push_test(p_user_id uuid) returns boolean
language plpgsql security definer set search_path='' as $$
declare claimed uuid;
begin
 insert into public.lcp_push_test_limits(user_id,last_sent_at) values(p_user_id,clock_timestamp())
 on conflict(user_id) do update set last_sent_at=excluded.last_sent_at where public.lcp_push_test_limits.last_sent_at < clock_timestamp()-interval '30 seconds'
 returning user_id into claimed;
 return claimed is not null;
end $$;
revoke all on function public.lcp_claim_push_test(uuid) from public,anon,authenticated;
grant execute on function public.lcp_claim_push_test(uuid) to service_role;
notify pgrst,'reload schema';
commit;
