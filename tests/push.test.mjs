import test from 'node:test';
import assert from 'node:assert/strict';
import '../push-model.js';
import {createHandler,safePushEndpoint} from '../supabase/functions/lcp-push-test/handler.mjs';
const model=globalThis.LcpPush;
const defaults=model.normalize();
const logo='https://jrlcofhpxvnlqzirjdbd.supabase.co/storage/v1/object/public/lcp-branding/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb.png';

test('Nederlandse standaardmelding en standaardlogo',()=>{
 const result=model.notification({},null);
 assert.equal(result.title,'LCP – Oproep');assert.equal(result.options.body,'Er is op de oproepknop gedrukt.');
 assert.equal(result.options.icon,'./icon-512.png');assert.equal(result.options.lang,'nl');
});
test('oude afzender behoudt apparaattekst, nieuwe titel komt uit instellingen',()=>{
 const result=model.notification({title:'LCP oproep',message:'De achterdeur staat open.',id:42},{title:'Deurbeveiliging',icon_url:logo});
 assert.equal(result.title,'Deurbeveiliging');assert.equal(result.options.body,'De achterdeur staat open.');
 assert.equal(result.options.tag,'lcp-42');assert.equal(result.options.icon,logo);
});
test('actuele servervoorkeuren vervangen verouderde lokale voorkeuren',()=>{
 const result=model.notification({message:'Oproep',lcp_preferences:{...defaults,title:'Nieuwe titel',icon_url:logo}},{...defaults,title:'Oude titel'});
 assert.equal(result.title,'Nieuwe titel');assert.equal(result.options.icon,logo);
});
test('ongeldige payload en een ontbrekende berichttekst geven Nederlandse terugval',()=>{
 for(const input of [null,42,'tekst',{}, {message:'  '}]) assert.equal(model.notification(input,null).options.body,defaults.default_message);
 assert.equal(model.notification({message:'',body:'Persoonlijke test'},null).options.body,'Persoonlijke test');
});
test('afbeeldingen zijn beperkt tot eigen publieke PNG-opslag',()=>{
 for(const url of ['javascript:alert(1)','https://evil.example/logo.png',logo+'?token=x',logo.replace('.png','.svg'),logo.replace('supabase.co','supabase.co.evil.example'),'//evil.example/logo.png']) assert.equal(model.safeIcon(url),defaults.icon_url);
 assert.equal(model.safeIcon(logo),logo);
});
test('lege en te lange voorkeuren worden geweigerd',()=>{
 for(const key of ['title','default_message','app_name'])assert.throws(()=>model.validate({...defaults,[key]:' '}));
 assert.throws(()=>model.validate({...defaults,title:'x'.repeat(101)}));assert.throws(()=>model.validate({...defaults,icon_url:'https://evil.example/a.png'}));
});

function fixture({role='admin',user=true,subError=false,rate=true,subs=[{endpoint:'https://web.push.apple.com/own-device',p256dh:'key',auth_secret:'secret'}],sendError=false,ready=true}={}){
 const queries=[],sent=[];
 const service={
  auth:{getUser:async token=>({data:{user:user?{id:'self'}:null},error:user?null:Error('invalid')})},
  from(table){
   const query={table};queries.push(query);
   return {select(columns){query.columns=columns;return this;},eq(key,value){query.filter=[key,value];return this;},
    async maybeSingle(){return {data:role?{role}:null,error:null};},
    async limit(n){query.limit=n;return {data:subs,error:subError?Error('database unavailable'):null};}};
  },
  async rpc(name,args){queries.push({rpc:name,args});return {data:rate,error:null};},
 };
 const handle=createHandler({service,ready,sendPush:async(sub,payload)=>{if(sendError)throw Error('failed');sent.push({sub,payload:JSON.parse(payload)});}});
 const request=(body={settings:{...defaults},message:'Persoonlijke test'},extra={})=>handle(new Request('https://function.example',{method:'POST',headers:{Authorization:'Bearer verified-user',Origin:'https://jkor95.github.io'},body:JSON.stringify(body),...extra}));
 return {request,queries,sent};
}

test('persoonlijke test filtert uitsluitend op de geverifieerde gebruiker',async()=>{
 const f=fixture();const response=await f.request();assert.equal(response.status,200);assert.equal((await response.json()).sent,1);
 const query=f.queries.find(q=>q.table==='lcp_push_subscriptions');assert.deepEqual(query.filter,['user_id','self']);
 assert.equal(f.sent[0].payload.message,'Persoonlijke test');assert.equal(f.sent[0].payload.lcp_preferences.title,defaults.title);
 assert.ok(f.queries.every(q=>q.table!=='lcp_calls'));assert.equal(f.sent.length,1);
});
test('bestaande PNG-logo’s in dezelfde bucket blijven bruikbaar',async()=>{
 const f=fixture();const response=await f.request({settings:{...defaults,icon_url:'https://jrlcofhpxvnlqzirjdbd.supabase.co/storage/v1/object/public/lcp-branding/logo.png'},message:'Persoonlijke test'});
 assert.equal(response.status,200);assert.ok(f.sent[0].payload.lcp_preferences.icon_url.endsWith('/logo.png'));
});
test('een aanvrager kan geen andere ontvanger of algemene oproep kiezen',async()=>{
 const f=fixture();const response=await f.request({settings:defaults,message:'Test',user_id:'other',broadcast:true});
 assert.equal(response.status,400);assert.equal(f.sent.length,0);
});
test('ontbrekende, ongeldige of onvoldoende autorisatie verstuurt niets',async()=>{
 for(const options of [{user:false},{role:'viewer'},{role:'operator'},{role:null}]){
  const f=fixture(options);const response=await f.request();assert.ok([401,403].includes(response.status));assert.equal(f.sent.length,0);
 }
 const f=fixture();assert.equal((await f.request(undefined,{headers:{}})).status,401);assert.equal(f.sent.length,0);
});
test('andere browserorigin wordt geweigerd',async()=>{
 const f=fixture();const response=await f.request(undefined,{headers:{Authorization:'Bearer token',Origin:'https://evil.example'}});
 assert.equal(response.status,403);assert.equal(f.sent.length,0);
});
test('geen abonnement, databasefout, ontbrekende configuratie en snel herhalen sturen niets',async()=>{
 for(const [options,status] of [[{subs:[]},409],[{subError:true},503],[{ready:false},503],[{rate:false},429]]){
  const f=fixture(options);assert.equal((await f.request()).status,status);assert.equal(f.sent.length,0);
 }
});
test('mislukte bezorging is geen geslaagde test',async()=>{
 const f=fixture({sendError:true});const response=await f.request();assert.equal(response.status,502);assert.equal((await response.json()).code,'DELIVERY_FAILED');
});
test('SSRF-bestemmingen en te grote aanvragen worden geweigerd',async()=>{
 for(const url of ['http://web.push.apple.com/x','https://127.0.0.1/x','https://web.push.apple.com.evil.example/x','https://web.push.apple.com:444/x','https://user:password@web.push.apple.com/x'])assert.equal(safePushEndpoint(url),false);
 const f=fixture({subs:[{endpoint:'https://127.0.0.1/x'}]});assert.equal((await f.request()).status,502);assert.equal(f.sent.length,0);
 const huge=fixture();assert.equal((await huge.request({message:'x'.repeat(17000)})).status,413);
});
