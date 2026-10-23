begin;
do $$
declare adm uuid; n integer;
begin
 select count(*) into n from public.lcp_devices where friendly_name in('LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve') and device_type='contact';
 if n<>4 then raise exception 'Niet alle vier deursensoren zijn beschikbaar.';end if;
 if not exists(select 1 from information_schema.columns where table_schema='public' and table_name='lcp_devices' and column_name='second_open_limit_minutes')
 or not exists(select 1 from information_schema.columns where table_schema='public' and table_name='lcp_devices' and column_name='message_second_open') then
  raise exception 'Instellingen voor tweede waarschuwing ontbreken.';end if;
 if position('left_open_again' in pg_get_functiondef('public.lcp_emit_sensor_event(text,text,uuid)'::regprocedure))=0 then
  raise exception 'Serverroute voor tweede waarschuwing ontbreekt.';end if;
 if not exists(select 1 from information_schema.columns where table_schema='public' and table_name='lcp_devices' and column_name='alert_tamper')
 or position('message_tamper' in pg_get_functiondef('public.lcp_emit_sensor_event(text,text,uuid)'::regprocedure))=0 then
  raise exception 'Sabotage-instellingen of serverroute ontbreken.';end if;
 if not exists(select 1 from pg_index i join pg_class c on c.oid=i.indexrelid where c.relname='lcp_calls_sensor_event_key_idx' and i.indisunique and i.indisvalid) then
  raise exception 'Beveiliging tegen dubbele sensorgebeurtenissen ontbreekt.';end if;
 select user_id into adm from public.lcp_members where role='admin' limit 1;
 if adm is null then raise exception 'Geen beheerder voor rechtencontrole.';end if;
 perform set_config('request.jwt.claim.sub',adm::text,true);
 set local role authenticated;
 select count(*) into n from public.lcp_devices where friendly_name in('LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve');
 if n<>4 then raise exception 'Beheerder kan sensoren niet lezen.';end if;
 update public.lcp_devices set message_closed=message_closed,
  alert_closed_when_armed=alert_closed_when_armed,long_alert_uses_schedule=long_alert_uses_schedule,
  second_open_limit_minutes=second_open_limit_minutes,message_second_open=message_second_open,
  alert_tamper=alert_tamper,message_tamper=message_tamper
 where friendly_name='LCP reserve';
 get diagnostics n=row_count;
 if n<>1 then raise exception 'Beheerder kan nieuwe sensorinstellingen niet opslaan.';end if;
 reset role;
 perform set_config('request.jwt.claim.sub',gen_random_uuid()::text,true);
 set local role authenticated;
 begin
  perform public.lcp_emit_sensor_event('LCP kantoor','opened',gen_random_uuid());
  raise exception 'Niet-lid kan een sensoroproep maken.';
 exception when insufficient_privilege then null;end;
 reset role;
 set local role anon;
 begin
  perform public.lcp_emit_sensor_event('LCP kantoor','opened',gen_random_uuid());
  raise exception 'Anonieme gebruiker kan een sensoroproep maken.';
 exception when insufficient_privilege then null;end;
 reset role;
end $$;
-- Geen echte sensoroproep of algemene testpush aanmaken.
select true as sensor_schema_and_access_passed;
rollback;
