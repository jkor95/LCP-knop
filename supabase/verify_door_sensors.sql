begin;
do $$
declare adm uuid; n integer;
begin
 select count(*) into n from public.lcp_devices where friendly_name in('LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve') and device_type='contact';
 if n<>4 then raise exception 'Niet alle vier deursensoren zijn beschikbaar.';end if;
 if not exists(select 1 from pg_index i join pg_class c on c.oid=i.indexrelid where c.relname='lcp_calls_sensor_event_key_idx' and i.indisunique and i.indisvalid) then
  raise exception 'Beveiliging tegen dubbele sensorgebeurtenissen ontbreekt.';end if;
 select user_id into adm from public.lcp_members where role='admin' limit 1;
 if adm is null then raise exception 'Geen beheerder voor rechtencontrole.';end if;
 perform set_config('request.jwt.claim.sub',adm::text,true);
 set local role authenticated;
 select count(*) into n from public.lcp_devices where friendly_name in('LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve');
 if n<>4 then raise exception 'Beheerder kan sensoren niet lezen.';end if;
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
