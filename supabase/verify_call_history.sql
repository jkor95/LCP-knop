begin;
do $$
declare adm uuid; stamp timestamptz; state jsonb;
begin
 if public.lcp_history_week_start('2026-10-18T21:59:59Z')<>'2026-10-11T22:00:00Z'::timestamptz
 or public.lcp_history_week_start('2026-10-18T22:00:00Z')<>'2026-10-18T22:00:00Z'::timestamptz
 or public.lcp_history_week_start('2026-10-25T23:00:00Z')<>'2026-10-25T23:00:00Z'::timestamptz then
  raise exception 'Weekgrens valt niet op maandag om 00.00 uur Nederlandse tijd.';
 end if;
 select user_id into adm from public.lcp_members where role='admin' limit 1;
 if adm is null then raise exception 'Geen beheerder voor de geschiedeniscontrole.';end if;
 perform set_config('request.jwt.claim.sub',adm::text,true);
 set local role authenticated;
 state:=public.lcp_get_call_history_state();
 if state->>'since' is null then raise exception 'Weekgrens ontbreekt.';end if;
 stamp:=public.lcp_reset_call_history();
 state:=public.lcp_get_call_history_state();
 if (state->>'since')::timestamptz<>stamp then raise exception 'Resetgrens is niet opgeslagen.';end if;
 reset role;
 perform set_config('request.jwt.claim.sub',gen_random_uuid()::text,true);
 set local role authenticated;
 begin
  perform public.lcp_reset_call_history();
  raise exception 'Onbevoegde gebruiker kan geschiedenis resetten.';
 exception when insufficient_privilege then null;end;
 begin
  perform public.lcp_get_call_history_state();
  raise exception 'Niet-lid kan geschiedenis lezen.';
 exception when insufficient_privilege then null;end;
 reset role;
end $$;
select true as history_checks_passed;
rollback;
