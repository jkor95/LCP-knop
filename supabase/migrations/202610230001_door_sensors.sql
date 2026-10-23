-- Breid bestaande apparaten uit. Behoud alle bestaande instellingen en RLS.
begin;
create temporary table lcp_sensor_before on commit drop as
 select id,to_jsonb(d)-array['alert_closed_when_armed','message_closed','long_alert_uses_schedule'] as settings
 from public.lcp_devices d;
alter table public.lcp_devices add column if not exists alert_closed_when_armed boolean not null default false;
alter table public.lcp_devices add column if not exists message_closed text not null default 'De deur is gesloten.'
 check(char_length(message_closed) between 1 and 240);
-- Voor oude sensoren blijft de bestaande, onafhankelijke timer behouden.
alter table public.lcp_devices add column if not exists long_alert_uses_schedule boolean not null default false;
alter table public.lcp_calls add column if not exists sensor_event_key uuid;
create unique index if not exists lcp_calls_sensor_event_key_idx on public.lcp_calls(sensor_event_key);

do $$ begin
 if exists(select 1 from public.lcp_devices where friendly_name in('LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve') and device_type<>'contact') then
  raise exception 'Een gewenste sensornaam is al gekoppeld aan een ander apparaattype.';
 end if;
end $$;
insert into public.lcp_devices(friendly_name,label,device_type,enabled,alert_open_when_armed,alert_closed_when_armed,
 alert_open_long,long_alert_uses_schedule,open_limit_minutes,arming_mode,schedule,message_open,message_closed,message_left_open)
values
 ('LCP kantoor','LCP kantoor','contact',true,true,true,false,true,5,'armed','[]',
  'De deur van het LCP-kantoor is geopend.','De deur van het LCP-kantoor is gesloten.','De deur van het LCP-kantoor staat al {minuten} minuten open.'),
 ('LCP nooddeur','LCP nooddeur','contact',true,true,true,true,true,5,'armed','[]',
  'De LCP-nooddeur is geopend.','De LCP-nooddeur is gesloten.','De LCP-nooddeur staat al {minuten} minuten open.'),
 ('TRAP nooddeur','TRAP nooddeur','contact',true,true,true,true,true,5,'armed','[]',
  'De TRAP-nooddeur is geopend.','De TRAP-nooddeur is gesloten.','De TRAP-nooddeur staat al {minuten} minuten open.'),
 ('LCP reserve','LCP reserve','contact',false,false,false,false,true,5,'armed','[]',
  'De reservedeur is geopend.','De reservedeur is gesloten.','De reservedeur staat al {minuten} minuten open.')
on conflict(friendly_name) do nothing;

create or replace function public.lcp_sensor_schedule_active(p_mode text,p_schedule jsonb,p_at timestamptz)
returns boolean language plpgsql immutable set search_path='' as $$
declare local_time timestamp; wd integer; prev integer; minute integer; period jsonb; a integer; b integer; days jsonb;
begin
 if p_mode='armed' then return true;end if;
 if p_mode is distinct from 'auto' then return false;end if;
 local_time:=p_at at time zone 'Europe/Amsterdam';wd:=extract(isodow from local_time)::integer;
 prev:=case when wd=1 then 7 else wd-1 end;minute:=extract(hour from local_time)::integer*60+extract(minute from local_time)::integer;
 for period in select value from jsonb_array_elements(p_schedule) loop
  begin
   days:=period->'days';
   a:=extract(hour from (period->>'start')::time)::integer*60+extract(minute from (period->>'start')::time)::integer;
   b:=extract(hour from (period->>'end')::time)::integer*60+extract(minute from (period->>'end')::time)::integer;
   if (a=b and days @> to_jsonb(array[wd]))
   or (a<b and days @> to_jsonb(array[wd]) and minute>=a and minute<b)
   or (a>b and ((days @> to_jsonb(array[wd]) and minute>=a) or (days @> to_jsonb(array[prev]) and minute<b))) then return true;end if;
  exception when others then continue;
  end;
 end loop;
 return false;
end $$;

-- SECURITY INVOKER: de bestaande lees- en INSERT-regels blijven gelden.
create or replace function public.lcp_emit_sensor_event(p_friendly_name text,p_kind text,p_event_key uuid)
returns boolean language plpgsql security invoker set search_path='' as $$
declare d public.lcp_devices; body text; created uuid;
begin
 if not exists(select 1 from public.lcp_members where user_id=(select auth.uid()) and role in('admin','operator')) then
  raise exception 'Geen toegang.' using errcode='42501';end if;
 if p_event_key is null or p_kind is null or p_kind not in('opened','closed','left_open') then
  raise exception 'Ongeldige sensorgebeurtenis.' using errcode='22023';end if;
 select * into d from public.lcp_devices where friendly_name=p_friendly_name and device_type='contact';
 if not found then raise exception 'Sensor niet gevonden.' using errcode='22023';end if;
 if not d.enabled then return false;end if;
 if p_kind='opened' then
  if not d.alert_open_when_armed then return false;end if;body:=d.message_open;
 elsif p_kind='closed' then
  if not d.alert_closed_when_armed then return false;end if;body:=d.message_closed;
 else
  if not d.alert_open_long then return false;end if;
  body:=replace(d.message_left_open,'{minuten}',d.open_limit_minutes::text);
 end if;
 if (p_kind<>'left_open' or d.long_alert_uses_schedule) and not public.lcp_sensor_schedule_active(d.arming_mode,d.schedule,statement_timestamp()) then return false;end if;
 insert into public.lcp_calls(source,message,created_by,sensor_event_key)
 values('zigbee',body,(select auth.uid()),p_event_key)
 on conflict(sensor_event_key) do nothing returning id into created;
 return created is not null;
end $$;
revoke all on function public.lcp_emit_sensor_event(text,text,uuid),public.lcp_sensor_schedule_active(text,jsonb,timestamptz) from public;
grant execute on function public.lcp_emit_sensor_event(text,text,uuid),public.lcp_sensor_schedule_active(text,jsonb,timestamptz) to authenticated;
do $$ begin
 if exists(select 1 from lcp_sensor_before b join public.lcp_devices d using(id)
  where b.settings is distinct from to_jsonb(d)-array['alert_closed_when_armed','message_closed','long_alert_uses_schedule']) then
  raise exception 'Bestaande apparaatinstellingen zijn gewijzigd; migratie teruggedraaid.';
 end if;
end $$;
notify pgrst,'reload schema';
commit;
