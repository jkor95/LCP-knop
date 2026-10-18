importScripts('./push-model.js');
const STORE='lcp-branding-v1';
function database() {
 return new Promise((resolve,reject)=>{const request=indexedDB.open(STORE,1);request.onupgradeneeded=()=>request.result.createObjectStore('settings');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
}
async function branding(write) {
 const db=await database();
 try {return await new Promise((resolve,reject)=>{
  const tx=db.transaction('settings',write?'readwrite':'readonly');const store=tx.objectStore('settings');
  const request=write?store.put(LcpPush.normalize(write),'global'):store.get('global');
  tx.oncomplete=()=>resolve(write || request.result || null);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
 });} finally {db.close();}
}
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('message',event=>{
 if(event.data?.type==='LCP_BRANDING') event.waitUntil(branding(event.data.settings).then(()=>event.ports[0]?.postMessage({ok:true})).catch(()=>event.ports[0]?.postMessage({ok:false})));
});
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(url.origin!==self.location.origin || !url.pathname.endsWith('/manifest.webmanifest')) return;
 event.respondWith((async()=>{
  const response=await fetch(new URL('./manifest.webmanifest',self.registration.scope),{cache:'no-store'});
  if(!response.ok)return response;
  const manifest=await response.json();const prefs=LcpPush.normalize(await branding().catch(()=>null));
  manifest.name=prefs.app_name;manifest.short_name=prefs.app_name;
  // Absolute URL's behouden dezelfde app-identiteit bij een gewijzigd logo.
  for(const key of ['id','start_url','scope']) manifest[key]=new URL(manifest[key],self.registration.scope).href;
  manifest.icons=[{src:new URL(prefs.icon_url,self.registration.scope).href,sizes:'512x512',type:'image/png',purpose:'any'}];
  return new Response(JSON.stringify(manifest),{headers:{'Content-Type':'application/manifest+json','Cache-Control':'no-store'}});
 })());
});
self.addEventListener('push',event=>{
 let data={};try{data=event.data.json();}catch{}
 event.waitUntil((async()=>{
  const cached=await branding().catch(()=>null);
  const message=LcpPush.notification(data,cached);
  await self.registration.showNotification(message.title,message.options);
 })());
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();
 event.waitUntil((async()=>{
  const url=new URL('./app.html',self.registration.scope).href;
  const clients=await self.clients.matchAll({type:'window',includeUncontrolled:true});
  const existing=clients.find(client=>client.url.startsWith(self.registration.scope));
  if(existing){await existing.focus();return;}await self.clients.openWindow(url);
 })());
});
