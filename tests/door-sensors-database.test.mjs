import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {PGlite}=await import(process.env.LCP_PGLITE_MODULE || '@electric-sql/pglite');
const migration=await readFile(new URL('../supabase/migrations/202610230001_door_sensors.sql',import.meta.url),'utf8');
const ADMIN='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',VIEWER='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
async function fixture(){
 const db=new PGlite();await db.exec(`
 create role anon;create role authenticated;create schema auth;
 create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
 grant usage on schema public,auth to anon,authenticated;
 create table public.lcp_members(user_id uuid primary key,role text);
 insert into public.lcp_members values('${ADMIN}','admin'),('${VIEWER}','viewer');
 grant select on public.lcp_members to authenticated;
 create table public.lcp_devices(id uuid primary key default gen_random_uuid(),friendly_name text unique not null,label text not null,device_type text not null,
 enabled boolean not null default false,message_button text not null default 'Knoptekst',message_open text not null default 'Open',message_left_open text not null default 'Al {minuten} minuten open',
 alert_open_when_armed boolean not null default true,alert_open_long boolean not null default true,open_limit_minutes int not null default 5,
 arming_mode text not null default 'auto',schedule jsonb not null default '[]',updated_at timestamptz not null default now());
 insert into public.lcp_devices(friendly_name,label,device_type,enabled,message_button) values('LCP_knop','Mediatheek','button',true,'Een leerling wacht op je.'),('LCP_deur','Oude deur','contact',false,'Knoptekst');
 create table public.lcp_calls(id uuid primary key default gen_random_uuid(),source text not null,message text not null,created_by uuid,created_at timestamptz default now());
 alter table public.lcp_calls enable row level security;
 create policy read_calls on public.lcp_calls for select to authenticated using(exists(select 1 from public.lcp_members where user_id=auth.uid()));
 create policy insert_calls on public.lcp_calls for insert to authenticated with check(created_by=auth.uid() and exists(select 1 from public.lcp_members where user_id=auth.uid() and role in('admin','operator')));
 alter table public.lcp_devices enable row level security;
 create policy read_devices on public.lcp_devices for select to authenticated using(exists(select 1 from public.lcp_members where user_id=auth.uid()));
 create policy change_devices on public.lcp_devices for all to authenticated using(exists(select 1 from public.lcp_members where user_id=auth.uid() and role='admin')) with check(exists(select 1 from public.lcp_members where user_id=auth.uid() and role='admin'));
 grant select,insert on public.lcp_calls to authenticated;grant select,insert,update,delete on public.lcp_devices to authenticated;
 create table push_counter(event uuid);
 create function count_push() returns trigger language plpgsql security definer as $$begin insert into public.push_counter values(new.id);return new;end$$;
 create trigger existing_push after insert on public.lcp_calls for each row execute function count_push();
 `);await db.exec(migration);return db;
}
async function as(db,role,uid=''){await db.exec(`reset role;set role ${role};set request.jwt.claim.sub='${uid}';`);}
async function emit(db,kind='opened',name='LCP nooddeur',key='cccccccc-cccc-cccc-cccc-cccccccccccc'){
 return (await db.query('select public.lcp_emit_sensor_event($1,$2,$3) as sent',[name,kind,key])).rows[0].sent;
}
test('vier standaarddeuren worden toegevoegd; bestaande knop en sensor blijven behouden',async()=>{
 const db=await fixture();try{
  const rows=(await db.query('select * from public.lcp_devices order by friendly_name')).rows;
  assert.equal(rows.length,6);
  assert.equal(rows.find(r=>r.friendly_name==='LCP_knop').message_button,'Een leerling wacht op je.');
  assert.equal(rows.find(r=>r.friendly_name==='LCP_deur').alert_closed_when_armed,false);
  for(const name of ['LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve']){
   const r=rows.find(r=>r.friendly_name===name);assert.equal(r.enabled,name!=='LCP reserve');
   assert.equal(r.alert_closed_when_armed,name!=='LCP reserve');assert.equal(r.arming_mode,'armed');
   assert.equal(r.alert_open_long,['LCP nooddeur','TRAP nooddeur'].includes(name));assert.equal(r.open_limit_minutes,5);
  }
  await db.exec("update public.lcp_devices set message_closed='Eigen tekst',enabled=false where friendly_name='LCP kantoor'");
  const before=(await db.query('select * from public.lcp_devices order by friendly_name')).rows;
  await db.exec(migration);
  assert.deepEqual((await db.query('select * from public.lcp_devices order by friendly_name')).rows,before);
 }finally{await db.close();}
});
test('herhaald aanbieden van een gebeurtenis maakt exact één oproep en push aan',async()=>{
 const db=await fixture();try{
  await as(db,'authenticated',ADMIN);
  assert.equal(await emit(db),true);assert.equal(await emit(db),false);
  assert.equal(await emit(db,'closed','LCP nooddeur','dddddddd-dddd-dddd-dddd-dddddddddddd'),true);
  const calls=(await db.query('select source,message,created_by from public.lcp_calls order by message')).rows;
  assert.equal(calls.length,2);assert.equal(calls[0].source,'zigbee');assert.equal(calls[0].created_by,ADMIN);
  await as(db,'postgres');assert.equal((await db.query('select count(*)::int as n from push_counter')).rows[0].n,2);
 }finally{await db.close();}
});
test('reservesensor, losse meldingopties en schema blokkeren ongewenste oproepen',async()=>{
 const db=await fixture();try{
  await as(db,'authenticated',ADMIN);
  assert.equal(await emit(db,'opened','LCP reserve'),false);
  assert.equal(await emit(db,'left_open','LCP kantoor'),false);
  await db.exec("update public.lcp_devices set arming_mode='disarmed' where friendly_name='LCP nooddeur'");
  for(const kind of ['opened','closed','left_open'])assert.equal(await emit(db,kind),false);
  await db.exec("update public.lcp_devices set long_alert_uses_schedule=false,open_limit_minutes=8,message_left_open='Al {minuten} minuten open' where friendly_name='LCP nooddeur'");
  assert.equal(await emit(db,'left_open'),true);
  assert.equal((await db.query('select message from public.lcp_calls')).rows[0].message,'Al 8 minuten open');
 }finally{await db.close();}
});
test('anonieme gebruikers en kijkers mogen geen sensoroproepen aanmaken',async()=>{
 const db=await fixture();try{
  await as(db,'anon');await assert.rejects(emit(db),{code:'42501'});
  await as(db,'authenticated',VIEWER);await assert.rejects(emit(db),{code:'42501'});
  assert.equal((await db.query("update public.lcp_devices set enabled=true where friendly_name='LCP reserve' returning id")).rows.length,0);
  await as(db,'authenticated',ADMIN);
  await assert.rejects(emit(db,'unknown'),{code:'22023'});
  await assert.rejects(emit(db,'opened','LCP_knop'),{code:'22023'});
  // De bestaande knop gebruikt nog steeds de oorspronkelijke INSERT-route.
  await db.query("insert into public.lcp_calls(source,message,created_by) values('zigbee','Bestaande knop',$1)",[ADMIN]);
  assert.equal((await db.query('select count(*)::int as n from public.lcp_calls')).rows[0].n,1);
 }finally{await db.close();}
});
test('server gebruikt Nederlandse tijd en ondersteunt een schema over middernacht',async()=>{
 const db=await fixture();try{
  const schedule=[{days:[5],start:'22:00',end:'06:00'}];
  for(const [at,expected] of [['2026-10-23T20:00:00Z',true],['2026-10-24T03:59:00Z',true],['2026-10-24T04:00:00Z',false]])
   assert.equal((await db.query("select public.lcp_sensor_schedule_active('auto',$1,$2) as active",[schedule,at])).rows[0].active,expected);
 }finally{await db.close();}
});

test('productiecontrole maakt geen echte oproep of push aan',async()=>{
 const db=await fixture();try{
  await db.exec(await readFile(new URL('../supabase/verify_door_sensors.sql',import.meta.url),'utf8'));
  assert.equal((await db.query('select count(*)::int as n from public.lcp_calls')).rows[0].n,0);
  assert.equal((await db.query('select count(*)::int as n from public.push_counter')).rows[0].n,0);
 }finally{await db.close();}
});
