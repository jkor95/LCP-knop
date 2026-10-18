const ORIGIN='https://jkor95.github.io';
function settings(value) {
 if(!value || typeof value!=='object')throw Error('INVALID_INPUT');
 for(const [key,max] of [['title',100],['default_message',240],['app_name',24]])if(typeof value[key]!=='string' || !value[key].trim() || [...value[key].trim()].length>max)throw Error('INVALID_INPUT');
 const icon=value.icon_url;
 if(typeof icon!=='string' || (!['./icon-192.png','./icon-512.png'].includes(icon) && !/^https:\/\/jrlcofhpxvnlqzirjdbd\.supabase\.co\/storage\/v1\/object\/public\/lcp-branding\/([A-Za-z0-9_-]+\/)*[A-Za-z0-9_.-]+\.png$/.test(icon)))throw Error('INVALID_INPUT');
 return {title:value.title.trim(),default_message:value.default_message.trim(),app_name:value.app_name.trim(),icon_url:icon};
}
export function safePushEndpoint(endpoint) {
 try {
  const u=new URL(endpoint);
  return u.protocol==='https:' && !u.username && !u.password && (!u.port || u.port==='443') &&
   (u.hostname==='web.push.apple.com' || u.hostname.endsWith('.push.apple.com') || u.hostname==='fcm.googleapis.com' || u.hostname==='updates.push.services.mozilla.com' || u.hostname.endsWith('.notify.windows.com'));
 } catch{return false;}
}
export function createHandler({service,sendPush,ready=true}) {
 return async request=>{
  const origin=request.headers.get('Origin');
  const headers={'Content-Type':'application/json','Access-Control-Allow-Origin':ORIGIN,'Access-Control-Allow-Headers':'authorization, apikey, content-type, x-client-info','Access-Control-Allow-Methods':'POST, OPTIONS','Vary':'Origin','Cache-Control':'no-store'};
  const reply=(status,body)=>new Response(JSON.stringify(body),{status,headers});
  if(origin && origin!==ORIGIN)return reply(403,{code:'FORBIDDEN'});
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers});
  if(request.method!=='POST')return reply(405,{code:'METHOD_NOT_ALLOWED'});
  if(!ready)return reply(503,{code:'NOT_CONFIGURED'});
  const match=/^Bearer (\S+)$/i.exec(request.headers.get('Authorization') || '');
  if(!match)return reply(401,{code:'UNAUTHORIZED'});
  try {
   const {data:{user},error:authError}=await service.auth.getUser(match[1]);
   if(authError || !user)return reply(401,{code:'UNAUTHORIZED'});
   const membership=await service.from('lcp_members').select('role').eq('user_id',user.id).maybeSingle();
   if(membership.error || membership.data?.role!=='admin')return reply(403,{code:'FORBIDDEN'});
   if(Number(request.headers.get('Content-Length'))>16384)return reply(413,{code:'INVALID_INPUT'});
   const raw=await request.text();if(raw.length>16384)return reply(413,{code:'INVALID_INPUT'});
   let body;try{body=JSON.parse(raw);}catch{return reply(400,{code:'INVALID_INPUT'});}
   if(!body || Object.keys(body).some(k=>!['settings','message'].includes(k)))return reply(400,{code:'INVALID_INPUT'});
   let prefs;try{prefs=settings(body.settings);}catch{return reply(400,{code:'INVALID_INPUT'});}
   if(typeof body.message!=='string' || !body.message.trim() || [...body.message.trim()].length>240)return reply(400,{code:'INVALID_INPUT'});
   // De ontvanger komt uitsluitend uit het geverifieerde JWT. Nooit uit de aanvraag.
   const result=await service.from('lcp_push_subscriptions').select('endpoint,p256dh,auth_secret').eq('user_id',user.id).limit(21);
   if(result.error)return reply(503,{code:'SUBSCRIPTIONS_UNAVAILABLE'});
   const subscriptions=result.data || [];
   if(!subscriptions.length)return reply(409,{code:'NO_SUBSCRIPTIONS'});
   if(subscriptions.length>20)return reply(409,{code:'TOO_MANY_SUBSCRIPTIONS'});
   const claim=await service.rpc('lcp_claim_push_test',{p_user_id:user.id});
   if(claim.error)return reply(503,{code:'NOT_CONFIGURED'});
   if(claim.data!==true)return reply(429,{code:'RATE_LIMITED'});
   const payload=JSON.stringify({id:'test-'+crypto.randomUUID(),message:body.message.trim(),lcp_preferences:prefs});
   let sent=0,failed=0;
   for(const sub of subscriptions){
    if(!safePushEndpoint(sub.endpoint)){failed++;continue;}
    try{await sendPush({endpoint:sub.endpoint,keys:{p256dh:sub.p256dh,auth:sub.auth_secret}},payload);sent++;}catch{failed++;}
   }
   // Bestaande registraties worden niet gewijzigd of verwijderd.
   return sent?reply(200,{sent,failed}):reply(502,{code:'DELIVERY_FAILED',sent:0,failed});
  }catch{return reply(503,{code:'TEMPORARILY_UNAVAILABLE'});}
 };
}
