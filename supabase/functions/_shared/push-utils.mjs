export function safePushEndpoint(endpoint) {
 try {
  const u=new URL(endpoint);
  return u.protocol==='https:' && !u.username && !u.password && (!u.port || u.port==='443') &&
   (u.hostname==='web.push.apple.com' || u.hostname.endsWith('.push.apple.com') || u.hostname==='fcm.googleapis.com' || u.hostname==='updates.push.services.mozilla.com' || u.hostname.endsWith('.notify.windows.com'));
 } catch{return false;}
}
export function displaySettings(row) {
 const clean=(value,fallback,max)=>typeof value==='string' && value.trim()?value.trim().slice(0,max):fallback;
 let icon=row?.icon_url || './icon-512.png';
 if(!['./icon-192.png','./icon-512.png'].includes(icon) && !/^https:\/\/jrlcofhpxvnlqzirjdbd\.supabase\.co\/storage\/v1\/object\/public\/lcp-branding\/([A-Za-z0-9_-]+\/)*[A-Za-z0-9_.-]+\.png$/.test(icon))icon='./icon-512.png';
 return {title:clean(row?.title,'LCP – Oproep',100),default_message:clean(row?.fallback_body,'Er is op de oproepknop gedrukt.',240),app_name:clean(row?.app_name,'LCP',24),icon_url:icon};
}
