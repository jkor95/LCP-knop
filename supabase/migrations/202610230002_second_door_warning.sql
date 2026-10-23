-- Tweede waarschuwing: tijd gerekend vanaf openen, maximaal eenmaal per cyclus.
begin;
do $$ begin
 if not exists(select 1 from information_schema.columns where table_schema='public' and table_name='lcp_devices' and column_name='second_open_limit_minutes') then
  alter table public.lcp_devices add column second_open_limit_minutes integer not null default 0 check(second_open_limit_minutes between 0 and 1440);
  update public.lcp_devices set second_open_limit_minutes=10 where friendly_name in('LCP nooddeur','TRAP nooddeur') and device_type='contact';
 end if;
end $$;
alter table public.lcp_devices add column if not exists message_second_open text not null default 'De deur staat nog steeds open na {minuten} minuten.' check(char_length(message_second_open) between 1 and 240);
create or replace function public.lcp_emit_sensor_event(p_friendly_name text,p_kind text,p_event_key uuid)
returns boolean language plpgsql security invoker set search_path='' as $$
declare d public.lcp_devices; body text; created uuid;
begin
 if not exists(select 1 from public.lcp_members where user_id=(select auth.uid()) and role in('admin','operator')) then
  raise exception 'Geen toegang.' using errcode='42501';end if;
 if p_event_key is null or p_kind is null or p_kind not in('opened','closed','left_open','left_open_again') then
  raise exception 'Ongeldige sensorgebeurtenis.' using errcode='22023';end if;
 select * into d from public.lcp_devices where friendly_name=p_friendly_name and device_type='contact';
 if not found then raise exception 'Sensor niet gevonden.' using errcode='22023';end if;
 if not d.enabled then return false;end if;
 if p_kind='opened' then
  if not d.alert_open_when_armed then return false;end if;body:=d.message_open;
 elsif p_kind='closed' then
  if not d.alert_closed_when_armed then return false;end if;body:=d.message_closed;
 elsif p_kind='left_open_again' then
  if not d.alert_open_long or d.second_open_limit_minutes<=d.open_limit_minutes then return false;end if;
  body:=replace(d.message_second_open,'{minuten}',d.second_open_limit_minutes::text);
 else
  if not d.alert_open_long then return false;end if;
  body:=replace(d.message_left_open,'{minuten}',d.open_limit_minutes::text);
 end if;
 if (p_kind not in('left_open','left_open_again') or d.long_alert_uses_schedule) and not public.lcp_sensor_schedule_active(d.arming_mode,d.schedule,statement_timestamp()) then return false;end if;
 insert into public.lcp_calls(source,message,created_by,sensor_event_key)
 values('zigbee',body,(select auth.uid()),p_event_key)
 on conflict(sensor_event_key) do nothing returning id into created;
 return created is not null;
end $$;
revoke all on function public.lcp_emit_sensor_event(text,text,uuid),public.lcp_sensor_schedule_active(text,jsonb,timestamptz) from public;
grant execute on function public.lcp_emit_sensor_event(text,text,uuid),public.lcp_sensor_schedule_active(text,jsonb,timestamptz) to authenticated;
notify pgrst,'reload schema';
commit;
