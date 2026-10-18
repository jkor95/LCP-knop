// Eenmalige onderhoudstest: geen oproep, uitsluitend Apple-registraties van de unieke beheerder.
import webpush from 'npm:web-push@3.6.7';
const root=Deno.env.get('RUNNER_TEMP') || '/tmp';
const {bindings,target}=JSON.parse(await Deno.readTextFile(root+'/lcp-own-push-test.json'));
const base='https://jrlcofhpxvnlqzirjdbd.supabase.co/functions/v1/';
// Deze aanvragen versturen niets: zij toetsen de echte toegangscontrole.
for(const [slug,field,expected] of [['lcp-push-test','code','UNAUTHORIZED'],['lcp-push-dispatch','melding','Geen toegang.']]){
 let ready=false;
 for(let attempt=0;attempt<8;attempt++){
  const response=await fetch(base+slug,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  let body;try{body=await response.json();}catch{body={};}
  if(response.status===401 && body[field]===expected){ready=true;break;}
  await new Promise(resolve=>setTimeout(resolve,2000));
 }
 if(!ready)throw Error('De gepubliceerde functie is nog niet correct bereikbaar: '+slug);
}
let result:{sent:number,failed:number,reason?:string}={sent:0,failed:0};
if(!bindings?.VAPID_PRIVATE_KEY)result.reason='Bestaande activering herkend; geen dubbele onderhoudstest verstuurd.';
else if(target.admin_count!==1)result.reason='Geen eenduidige beheerder; geen test verstuurd.';
else if(target.subscriptions?.length>20)result.reason='Te veel iPhone-registraties; controleer de doelgroep voordat een test wordt verstuurd.';
else if(!target.subscriptions?.length)result.reason='Geen geregistreerde iPhone van de beheerder gevonden.';
else {
 webpush.setVapidDetails(bindings.VAPID_SUBJECT,bindings.VAPID_PUBLIC_KEY,bindings.VAPID_PRIVATE_KEY);
 const prefs={...target.settings,icon_url:target.settings.icon_url || './icon-512.png'};
 const payload=JSON.stringify({id:'persoonlijke-test-'+crypto.randomUUID(),message:'Dit is een persoonlijke LCP-testmelding. De nieuwe pushinstellingen zijn actief.',lcp_preferences:prefs});
 for(const subscription of target.subscriptions){
  const url=new URL(subscription.endpoint);
  if(url.origin!=='https://web.push.apple.com'){result.failed++;continue;}
  try{await webpush.sendNotification(subscription,payload,{TTL:60,urgency:'normal',timeout:10000});result.sent++;}
  catch{result.failed++;}
 }
}
await Deno.writeTextFile(root+'/lcp-own-push-result.json',JSON.stringify(result));
console.log(result.reason || `Persoonlijke iPhone-test: ${result.sent} aangeboden, ${result.failed} mislukt. Geen algemene oproep aangemaakt.`);
