
begin;
create temporary table lcp_verify_result(check_name text primary key,passed boolean) on commit drop;
do $$
declare adm uuid; member_id uuid; original jsonb; changed jsonb;
begin
 select user_id into adm from public.lcp_members where role='admin' limit 1;
 if adm is null then raise exception 'Geen beheerder om toegangsregels te controleren.';end if;
 perform set_config('request.jwt.claim.sub',adm::text,true);
 set local role authenticated;
 original:=public.lcp_get_push_settings();
 changed:=public.lcp_save_push_settings(original || jsonb_build_object('title','LCP – tijdelijke toegangscontrole','icon_url',coalesce(nullif(original->>'icon_url',''),'./icon-512.png')),(original->>'updated_at')::timestamptz);
 if changed->>'title'<>'LCP – tijdelijke toegangscontrole' then raise exception 'Opslaan als beheerder werkt niet.';end if;
 reset role;
 insert into lcp_verify_result values('admin_can_read_and_save',true);
 select user_id into member_id from public.lcp_members where role<>'admin' limit 1;
 if member_id is not null then
  perform set_config('request.jwt.claim.sub',member_id::text,true);
  set local role authenticated;
  perform public.lcp_get_push_settings();
  begin
   perform public.lcp_save_push_settings(changed,(changed->>'updated_at')::timestamptz);
   raise exception 'Een gewoon lid kan instellingen schrijven.';
  exception when insufficient_privilege then null;end;
  reset role;
  insert into lcp_verify_result values('member_can_read_not_write',true);
 end if;
 perform set_config('request.jwt.claim.sub',gen_random_uuid()::text,true);
 set local role authenticated;
 begin
  perform public.lcp_get_push_settings();
  raise exception 'Een niet-lid kan instellingen lezen.';
 exception when insufficient_privilege then null;end;
 begin
  perform public.lcp_save_push_settings(original,(changed->>'updated_at')::timestamptz);
  raise exception 'Een niet-beheerder kan instellingen schrijven.';
 exception when insufficient_privilege then null;end;
 reset role;
 insert into lcp_verify_result values('non_member_denied',true);
 perform set_config('request.jwt.claim.sub','',true);
 set local role anon;
 begin
  perform public.lcp_get_push_settings();
  raise exception 'Anonieme instellingen zijn niet afgeschermd.';
 exception when insufficient_privilege then null;end;
 reset role;
 insert into lcp_verify_result values('anonymous_denied',true);
end $$;
select jsonb_agg(to_jsonb(r)) as checks from lcp_verify_result r;
rollback;
