self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('push',e=>{
 let d={};try{d=e.data.json()}catch{}
 e.waitUntil(self.registration.showNotification('LCP oproep',{body:d.message||'Nieuwe oproep',tag:'lcp-'+(d.id||Date.now()),icon:'./icon-192.png',badge:'./icon-192.png',data:{url:'./app.html'}}));
});
self.addEventListener('notificationclick',e=>{
 e.notification.close();
 e.waitUntil((async()=>{const url=new URL(e.notification.data?.url||'./app.html',self.registration.scope).href;const clients=await self.clients.matchAll({type:'window',includeUncontrolled:true});const existing=clients.find(c=>c.url.startsWith(self.registration.scope));if(existing){await existing.focus();return;}await self.clients.openWindow(url)})());
});