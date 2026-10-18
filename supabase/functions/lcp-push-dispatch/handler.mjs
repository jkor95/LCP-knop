import {safePushEndpoint,displaySettings} from '../_shared/push-utils.mjs';
// Zelfde webhook, oproepen, VAPID-sleutels en geregistreerde apparaten.
export function createDispatchHandler({service,sendPush,webhookToken}) {
 return async req=>{
  const reply=(status,body)=>Response.json(body,{status});
  if(req.method!=='POST' || !webhookToken || req.headers.get('x-lcp-webhook-token')!==webhookToken)return reply(401,{melding:'Geen toegang.'});
  let body;try{const raw=await req.text();if(raw.length>4096)return reply(400,{melding:'Ongeldige aanvraag.'});body=JSON.parse(raw);}catch{return reply(400,{melding:'Ongeldige aanvraag.'});}
  const id=body?.id;
  if(typeof id!=='string' || !/^[0-9a-f-]{36}$/i.test(id))return reply(400,{melding:'Ongeldig oproepnummer.'});
  try {
   const result=await service.from('lcp_calls').select('id,message').eq('id',id).maybeSingle();
   if(result.error || !result.data)return reply(404,{melding:'Oproep niet gevonden.'});
   const call=result.data;
   const preference=await service.from('lcp_push_preferences').select('title,fallback_body,app_name,icon_url').maybeSingle();
   const prefs=displaySettings(preference.error?null:preference.data);
   const members=await service.from('lcp_members').select('user_id');
   if(members.error)return reply(503,{melding:'Ontvangers controleren is niet gelukt.'});
   const allowed=(members.data || []).map(member=>member.user_id);
   if(!allowed.length)return reply(200,{sent:0,failed:0});
   const subscriptions=await service.from('lcp_push_subscriptions').select('id,endpoint,p256dh,auth_secret').in('user_id',allowed);
   if(subscriptions.error)return reply(503,{melding:'Pushregistraties laden is niet gelukt.'});
   const payload=JSON.stringify({id:call.id,message:typeof call.message==='string' && call.message.trim()?call.message:prefs.default_message,url:'./app.html',lcp_preferences:prefs});
   const outcomes=await Promise.allSettled((subscriptions.data || []).map(async sub=>{
    if(!safePushEndpoint(sub.endpoint))throw Error('Ongeldige pushbestemming.');
    try{await sendPush({endpoint:sub.endpoint,keys:{p256dh:sub.p256dh,auth:sub.auth_secret}},payload);}
    catch(error){
     // Bestaande opruiming blijft beperkt tot registraties die de pushdienst verlopen noemt.
     if(error.statusCode===404 || error.statusCode===410)await service.from('lcp_push_subscriptions').delete().eq('id',sub.id);
     else throw error;
    }
   }));
   return reply(200,{sent:outcomes.filter(item=>item.status==='fulfilled').length,failed:outcomes.filter(item=>item.status==='rejected').length});
  }catch{return reply(503,{melding:'Pushmeldingen versturen is tijdelijk niet gelukt.'});}
 };
}
