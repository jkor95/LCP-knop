-- Reset uitsluitend de zichtbare geschiedenis. Laat oproepen, triggers,
-- registraties en de Windows-worker ongemoeid.
begin;
create table if not exists public.lcp_call_history_state (
 id boolean primary key default true check(id),
 reset_at timestamptz,
 reset_by uuid
);
insert into public.lcp_call_history_state(id) values(true) on conflict(id) do nothing;
alter table public.lcp_call_history_state enable row level security;
revoke all on public.lcp_call_history_state from anon,authenticated;

create or replace function public.lcp_history_week_start(p_at timestamptz)
returns timestamptz language sql immutable set search_path='' as $$
 select date_trunc('week',p_at at time zone 'Europe/Amsterdam')
  at time zone 'Europe/Amsterdam'
$$;
revoke all on function public.lcp_history_week_start(timestamptz) from public;

create or replace function public.lcp_get_call_history_state() returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare stamp timestamptz; week_start timestamptz;
begin
 if not public.lcp_push_is_member() then raise exception 'Geen toegang.' using errcode='42501'; end if;
 select reset_at into stamp from public.lcp_call_history_state where id=true;
 week_start:=public.lcp_history_week_start(statement_timestamp());
 return jsonb_build_object('since',greatest(week_start,stamp),'week_start',week_start,'reset_at',stamp);
end $$;

create or replace function public.lcp_reset_call_history() returns timestamptz
language plpgsql security definer set search_path='' as $$
declare stamp timestamptz;
begin
 if not public.lcp_push_is_admin() then raise exception 'Alleen beheerders mogen de geschiedenis resetten.' using errcode='42501'; end if;
 -- De WHERE-voorwaarde is vereist door Supabase safeupdate.
 update public.lcp_call_history_state set reset_at=clock_timestamp(),reset_by=(select auth.uid()) where id=true returning reset_at into stamp;
 if stamp is null then raise exception 'De geschiedenisinstelling ontbreekt.'; end if;
 return stamp;
end $$;
revoke all on function public.lcp_get_call_history_state(),public.lcp_reset_call_history() from public;
grant execute on function public.lcp_get_call_history_state(),public.lcp_reset_call_history() to authenticated;
notify pgrst,'reload schema';
commit;
