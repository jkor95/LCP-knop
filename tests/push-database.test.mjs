// PostgreSQL (PGlite) integratietests voor de echte migratie en RLS-regels.
// LCP_PGLITE_MODULE kan wijzen naar een externe installatie van @electric-sql/pglite.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {PGlite}=await import(process.env.LCP_PGLITE_MODULE || '@electric-sql/pglite');
const migration=await readFile(new URL('../supabase/migrations/202610180001_push_settings.sql',import.meta.url),'utf8');
const ADMIN='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',MEMBER='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
const originalDate='2026-10-01T10:00:00Z';
const input={title:'LCP – Receptie',default_message:'Er wacht iemand.',app_name:'LCP',icon_url:'./icon-512.png'};
async function fixture(){
 const db=new PGlite();
 await db.exec(`
 create role anon;create role authenticated;create role service_role bypassrls;
 create schema auth;create schema storage;
 create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
 grant usage on schema auth,public,storage to anon,authenticated,service_role;
 create table public.lcp_members(user_id uuid primary key,role text);
 insert into public.lcp_members values('${ADMIN}','admin'),('${MEMBER}','viewer');
 create table public.lcp_push_preferences(id int primary key default 1,title text,icon_url text,updated_at timestamptz default now());
 insert into public.lcp_push_preferences values(1,'Bestaande titel',null,'${originalDate}');
 alter table public.lcp_push_preferences enable row level security;
 create policy old_permissive on public.lcp_push_preferences for all to anon,authenticated using(true) with check(true);
 grant all on public.lcp_push_preferences to anon,authenticated,service_role;
 create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
 insert into storage.buckets values('lcp-branding','lcp-branding',true,2097152,array['image/png']);
 create table storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text,name text,metadata jsonb);
 alter table storage.objects enable row level security;
 create policy old_storage_permissive on storage.objects for all to anon,authenticated using(true) with check(true);
 grant all on storage.objects to anon,authenticated,service_role;
 `);
 await db.exec(migration);
 return db;
}
async function as(db,role,uid='') {await db.exec(`reset role;set role ${role};set request.jwt.claim.sub='${uid}';`);}
async function save(db,stamp=originalDate){return db.query('select public.lcp_save_push_settings($1::jsonb,$2::timestamptz) as settings',[JSON.stringify(input),stamp]);}

test('migratie hergebruikt de voorkeurenrij en bestaande bucket en is herhaalbaar',async()=>{
 const db=await fixture();try{
  await db.exec(migration);
  const {rows:[row]}=await db.query('select * from public.lcp_push_preferences');
  assert.equal(row.id,1);assert.equal(row.title,'Bestaande titel');assert.equal(row.icon_url,null);
  assert.equal(row.fallback_body,'Er is op de oproepknop gedrukt.');
  assert.equal((await db.query('select count(*)::int as n from storage.buckets')).rows[0].n,1);
 }finally{await db.close();}
});
test('alleen beheerder kan opslaan; bestaande datum beschermt tegen overschrijven',async()=>{
 const db=await fixture();try{
  await as(db,'authenticated',MEMBER);
  assert.equal((await db.query('select public.lcp_get_push_settings() as s')).rows[0].s.title,'Bestaande titel');
  await assert.rejects(save(db),{code:'42501'});
  await db.exec("update public.lcp_push_preferences set title='Verboden wijziging'");
  assert.equal((await db.query('select title from public.lcp_push_preferences')).rows[0].title,'Bestaande titel');
  await db.exec('delete from public.lcp_push_preferences');
  assert.equal((await db.query('select count(*)::int as n from public.lcp_push_preferences')).rows[0].n,1);
  await as(db,'authenticated',ADMIN);
  const row=(await save(db)).rows[0].settings;assert.equal(row.title,input.title);
  const legacy={...input,icon_url:'https://jrlcofhpxvnlqzirjdbd.supabase.co/storage/v1/object/public/lcp-branding/logo.png'};
  const changed=await db.query('select public.lcp_save_push_settings($1::jsonb,$2::timestamptz) as settings',[JSON.stringify(legacy),row.updated_at]);
  assert.equal(changed.rows[0].settings.icon_url,legacy.icon_url);
  await assert.rejects(save(db),{code:'40001'});
 }finally{await db.close();}
});
test('anonieme aanvragen zien geen instellingen en kunnen niet schrijven',async()=>{
 const db=await fixture();try{
  await as(db,'anon');
  assert.equal((await db.query('select count(*)::int as n from public.lcp_push_preferences')).rows[0].n,0);
  await assert.rejects(db.query('select public.lcp_get_push_settings()'),{code:'42501'});
  await assert.rejects(db.exec("insert into public.lcp_push_preferences(id,title) values(2,'Verboden')"),{code:'42501'});
  await assert.rejects(db.exec("insert into storage.objects(bucket_id,name,metadata) values('lcp-branding','hack.png','{\"mimetype\":\"image/png\"}')"),{code:'42501'});
 }finally{await db.close();}
});
test('opslag weigert niet-beheerders, vreemde paden, updates en onjuiste MIME-types',async()=>{
 const db=await fixture();const path=ADMIN+'/cccccccc-cccc-cccc-cccc-cccccccccccc.png';
 try{
  await as(db,'authenticated',MEMBER);
  await assert.rejects(db.query('insert into storage.objects(bucket_id,name,metadata) values($1,$2,$3)',['lcp-branding',path,{mimetype:'image/png'}]),{code:'42501'});
  await as(db,'authenticated',ADMIN);
  await db.query('insert into storage.objects(bucket_id,name,metadata) values($1,$2,$3)',['lcp-branding',path,{mimetype:'image/png'}]);
  await assert.rejects(db.query('insert into storage.objects(bucket_id,name,metadata) values($1,$2,$3)',['lcp-branding',path,{mimetype:'image/svg+xml'}]),{code:'42501'});
  await assert.rejects(db.query('insert into storage.objects(bucket_id,name,metadata) values($1,$2,$3)',['lcp-branding',path.replace(ADMIN,MEMBER),{mimetype:'image/png'}]),{code:'42501'});
  await db.exec("update storage.objects set name='vervangen.png'");
  assert.equal((await db.query('select name from storage.objects')).rows[0].name,path);
 }finally{await db.close();}
});
test('logo-validatie zit ook in de database en testlimiet is alleen voor de server',async()=>{
 const db=await fixture();try{
  await as(db,'authenticated',ADMIN);
  await assert.rejects(db.query('select public.lcp_save_push_settings($1::jsonb,$2::timestamptz)',[JSON.stringify({...input,icon_url:'https://evil.example/a.png'}),originalDate]),{code:'22023'});
  await assert.rejects(db.query('select public.lcp_claim_push_test($1)',[ADMIN]),{code:'42501'});
  await as(db,'service_role');
  assert.equal((await db.query('select public.lcp_claim_push_test($1) as ok',[ADMIN])).rows[0].ok,true);
  assert.equal((await db.query('select public.lcp_claim_push_test($1) as ok',[ADMIN])).rows[0].ok,false);
  assert.equal((await db.query('select title from public.lcp_push_preferences')).rows[0].title,'Bestaande titel');
 }finally{await db.close();}
});
test('productiecontrole doorloopt echte rollen en draait de tijdelijke wijziging terug',async()=>{
 const db=await fixture();try{
  const before=(await db.query('select * from public.lcp_push_preferences')).rows;
  const sql=await readFile(new URL('../supabase/verify_push_settings.sql',import.meta.url),'utf8');
  await db.exec(sql);
  assert.deepEqual((await db.query('select * from public.lcp_push_preferences')).rows,before);
 }finally{await db.close();}
});
