import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {PGlite}=await import(process.env.LCP_PGLITE_MODULE || '@electric-sql/pglite');
const migration=await readFile(new URL('../supabase/migrations/202610180003_call_history.sql',import.meta.url),'utf8');
const ADMIN='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',MEMBER='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
async function fixture(){
 const db=new PGlite();
 await db.exec(`create role anon;create role authenticated;
 create schema auth;
 create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
 grant usage on schema public,auth to anon,authenticated;
 create table public.lcp_members(user_id uuid primary key,role text);
 insert into public.lcp_members values('${ADMIN}','admin'),('${MEMBER}','viewer');
 create function public.lcp_push_is_member() returns boolean language sql stable security definer set search_path='' as $$select exists(select 1 from public.lcp_members where user_id=auth.uid())$$;
 create function public.lcp_push_is_admin() returns boolean language sql stable security definer set search_path='' as $$select exists(select 1 from public.lcp_members where user_id=auth.uid() and role='admin')$$;
 create table public.lcp_calls(id int primary key,message text,created_at timestamptz);
 insert into public.lcp_calls values(1,'Bestaande oproep',now()-interval '1 day');`);
 await db.exec(migration);return db;
}
async function as(db,role,uid=''){await db.exec(`reset role;set role ${role};set request.jwt.claim.sub='${uid}';`);}
test('zondaggrens geldt in Nederland, inclusief zomer- en wintertijd',async()=>{
 const db=await fixture();try{
  for(const [at,expected] of [
   ['2026-10-17T21:59:59Z','2026-10-10T22:00:00.000Z'],
   ['2026-10-17T22:00:00Z','2026-10-17T22:00:00.000Z'],
   ['2026-10-25T02:30:00Z','2026-10-24T22:00:00.000Z'],
   ['2026-11-01T12:00:00Z','2026-10-31T23:00:00.000Z'],
   ['2026-03-29T10:00:00Z','2026-03-28T23:00:00.000Z'],
  ])assert.equal((await db.query('select public.lcp_history_week_start($1) as stamp',[at])).rows[0].stamp.toISOString(),expected);
 }finally{await db.close();}
});
test('reset werkt voor iedereen, bewaart oproeprecords en laat nieuwe oproepen door',async()=>{
 const db=await fixture();try{
  const before=(await db.query('select * from public.lcp_calls')).rows;
  await as(db,'authenticated',ADMIN);
  const reset=(await db.query('select public.lcp_reset_call_history() as stamp')).rows[0].stamp;
  await as(db,'authenticated',MEMBER);
  const state=(await db.query('select public.lcp_get_call_history_state() as state')).rows[0].state;
  assert.equal(new Date(state.since).toISOString(),reset.toISOString());
  await as(db,'postgres');
  assert.deepEqual((await db.query('select * from public.lcp_calls')).rows,before);
  await db.query("insert into public.lcp_calls values(2,'Nieuwe oproep',$1::timestamptz+interval '1 second')",[state.since]);
  assert.deepEqual((await db.query('select id from public.lcp_calls where created_at >= $1',[state.since])).rows,[{id:2}]);
  await db.exec(migration);
  assert.equal((await db.query('select reset_at from public.lcp_call_history_state')).rows[0].reset_at.toISOString(),reset.toISOString());
 }finally{await db.close();}
});
test('alleen beheerder mag resetten; niet-leden en anonieme gebruikers worden geweigerd',async()=>{
 const db=await fixture();try{
  await as(db,'authenticated',MEMBER);
  await db.query('select public.lcp_get_call_history_state()');
  await assert.rejects(db.query('select public.lcp_reset_call_history()'),{code:'42501'});
  await assert.rejects(db.exec('update public.lcp_call_history_state set reset_at=now() where id=true'),{code:'42501'});
  await as(db,'authenticated','cccccccc-cccc-cccc-cccc-cccccccccccc');
  await assert.rejects(db.query('select public.lcp_get_call_history_state()'),{code:'42501'});
  await as(db,'anon');
  for(const f of ['lcp_get_call_history_state','lcp_reset_call_history'])await assert.rejects(db.query(`select public.${f}()`),{code:'42501'});
 }finally{await db.close();}
});
test('productiecontrole reset uitsluitend binnen een teruggedraaide transactie',async()=>{
 const db=await fixture();try{
  const original=(await db.query('select * from public.lcp_call_history_state')).rows;
  await db.exec(await readFile(new URL('../supabase/verify_call_history.sql',import.meta.url),'utf8'));
  assert.deepEqual((await db.query('select * from public.lcp_call_history_state')).rows,original);
 }finally{await db.close();}
});
