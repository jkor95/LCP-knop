import './push-model.js';
export class LcpError extends Error {}
export function pushSaveError(error) {
  const code=String(error?.code || '');
  const messages={
    '40001':'De instellingen zijn intussen gewijzigd. Herlaad de pagina voordat je opnieuw opslaat.',
    '42501':'Opslaan is geweigerd. Log opnieuw in met je beheerdersaccount en probeer opnieuw.',
    '22023':'De server heeft een titel, berichttekst, appnaam of PNG-logo afgekeurd. Controleer deze velden.',
    PGRST301:'Je sessie is verlopen. Log opnieuw in en probeer opnieuw.',
    PGRST302:'Je bent niet meer ingelogd. Log opnieuw in en probeer opnieuw.',
    PGRST303:'Je sessie is niet geldig. Log opnieuw in en probeer opnieuw.',
    PGRST202:'De opslagfunctie is nog niet beschikbaar bij de server. Probeer het over een minuut opnieuw.',
  };
  // Toon alleen een begrensde foutcode, nooit ruwe databaseberichten of verzoekgegevens.
  const reference=/^[A-Z0-9]{5,10}$/.test(code)?` (foutcode ${code})`:'';
  return new LcpError((messages[code] || 'Pushinstellingen zijn niet opgeslagen door een verbindings- of serverfout. Geef de foutcode door aan de beheerder.')+reference);
}
export const pushModel = globalThis.LcpPush;
export async function readPushSettings(db) {
  const {data,error} = await db.rpc('lcp_get_push_settings');
  if (error) throw new LcpError('Pushinstellingen zijn nog niet beschikbaar. De beheerder moet de Supabase-uitbreiding activeren.');
  return pushModel.normalize(data);
}
export async function applyBranding(settings) {
  const prefs = pushModel.normalize(settings);
  document.querySelectorAll('[data-lcp-logo]').forEach(img => { img.src=prefs.icon_url; img.onerror=()=>{img.onerror=null;img.src='./icon-512.png';}; });
  document.querySelectorAll('[data-lcp-name]').forEach(node => node.textContent=prefs.app_name);
  document.querySelector('meta[name="apple-mobile-web-app-title"]')?.setAttribute('content',prefs.app_name);
  document.querySelector('link[rel="apple-touch-icon"]')?.setAttribute('href',prefs.icon_url);
  if (!('serviceWorker' in navigator)) return;
  try {
    const reg = await navigator.serviceWorker.ready;
    // Het antwoord bevestigt dat de worker de voorkeuren duurzaam heeft opgeslagen.
    const channel = new MessageChannel();
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('Opslaan van de lokale pushweergave duurt te lang.')),4000);
      channel.port1.onmessage=event=>{clearTimeout(timer);channel.port1.close();event.data?.ok?resolve():reject(Error('Lokale pushweergave niet opgeslagen.'));};
      (reg.active || navigator.serviceWorker.controller)?.postMessage({type:'LCP_BRANDING',settings:prefs},[channel.port2]);
    });
    const manifest=document.querySelector('link[rel="manifest"]');
    if (manifest && navigator.serviceWorker.controller) manifest.href='./manifest.webmanifest?branding='+encodeURIComponent(prefs.updated_at || 'standaard');
  } catch (error) { console.warn('Lokale pushweergave kon niet worden bijgewerkt.',error); }
}
export function sourceLabel(value) {
  return {test:'Testoproep',web:'Webapp',zigbee:'Zigbee-knop of sensor',button:'Oproepknop',sensor:'Sensor',door:'Deursensor',manual:'Handmatige oproep',windows:'Windows-knop'}[value] || 'Oproep';
}
export function dutchError(error) {
  if (typeof error === 'string') return error;
  const message=String(error?.message || '');
  if(error instanceof LcpError || /^(Kies eerst|Kies voor elk|Vul een naam|Aantal minuten|Iedere meldtekst|Deze browser ondersteunt|Audio is nog)/.test(message)) return message;
  if (/invalid login credentials/i.test(message)) return 'Het e-mailadres of wachtwoord is onjuist.';
  if (/email not confirmed/i.test(message)) return 'Bevestig eerst je e-mailadres.';
  if (/fetch|network|timeout|failed to send/i.test(message)) return 'De verbinding is onderbroken. Controleer je internetverbinding en probeer opnieuw.';
  return 'De bewerking is niet gelukt. Controleer je toegang en probeer opnieuw.';
}
export async function sendPersonalTest(db,settings,message) {
  const prefs=pushModel.validate(settings);
  if(typeof message!=='string' || !message.trim() || message.trim().length>240)throw new LcpError('De testtekst moet 1 tot 240 tekens bevatten.');
  const {data,error}=await db.functions.invoke('lcp-push-test',{body:{settings:prefs,message:message.trim()}});
  if(error){
    let code;try{code=(await error.context?.json())?.code;}catch{}
    throw new LcpError({NO_SUBSCRIPTIONS:'Je hebt nog geen geregistreerd apparaat. Open LCP op je iPhone en schakel pushmeldingen in.',FORBIDDEN:'Alleen een LCP-beheerder mag deze test versturen.',RATE_LIMITED:'Wacht 30 seconden voordat je opnieuw een test verstuurt.',DELIVERY_FAILED:'De pushdienst heeft de testmelding niet geaccepteerd. Controleer de pushregistratie op je iPhone.'}[code] || 'Testmelding niet verstuurd. De persoonlijke pushfunctie is mogelijk nog niet geactiveerd.');
  }
  if(!Number.isInteger(data?.sent) || data.sent<1)throw new LcpError('Er is geen testmelding verstuurd. Controleer de pushregistratie op je iPhone.');
  return data.sent;
}
