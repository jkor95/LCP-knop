import {pushModel,readPushSettings,applyBranding,sendPersonalTest,LcpError} from './push-client.js';

// Behoud de bestaande apparaatinstellingen; deze module beheert alleen de extra secties.
export function mountPushSettings(db, getDeviceMessage) {
 const el=id=>document.getElementById(id);
 let saved=null,draftIcon=pushModel.DEFAULTS.icon_url,pendingLogo=null,previewUrl=null,available=false;
 const inputs=['pushTitle','pushMessage','pushAppName','pushLogo','chooseLogo','resetLogo','savePush','sendPushTest'];
 const report=(text,error=false)=>{el('pushStatus').textContent=text;el('pushStatus').className=error?'push-error':'sub';};
 function values(){return {title:el('pushTitle').value.trim(),default_message:el('pushMessage').value.trim(),app_name:el('pushAppName').value.trim(),icon_url:draftIcon};}
 function message(){return el('previewKind').value==='default'?values().default_message:getDeviceMessage(el('previewKind').value) || values().default_message;}
 function preview(){
  const prefs=pushModel.normalize(values());
  el('previewTitle').textContent=prefs.title;el('previewBody').textContent=message() || prefs.default_message;
  el('previewAppName').textContent=prefs.app_name;el('previewLogo').src=previewUrl || prefs.icon_url;
  el('logoPreview').src=previewUrl || prefs.icon_url;
 }
 function fill(settings){
  saved=settings;draftIcon=settings.icon_url;
  el('pushTitle').value=settings.title;el('pushMessage').value=settings.default_message;el('pushAppName').value=settings.app_name;
  preview();
 }
 function lock(busy){inputs.forEach(id=>el(id).disabled=busy || !available);}
 async function load(){
  lock(true);
  try {fill(await readPushSettings(db));available=true;report('Pushinstellingen geladen. Bestaande apparaatteksten blijven behouden.');}
  catch {fill(pushModel.normalize());report('De uitbreiding voor pushinstellingen is nog niet geactiveerd. Je bestaande apparaatinstellingen blijven werken. De getoonde standaardwaarden zijn nog niet opgeslagen.',true);}
  finally {lock(false);}
 }
 async function save(){
  lock(true);let uploaded=null;
  try {
   const draft=pushModel.validate(values());
   if(pendingLogo){
    const {data:{user},error:authError}=await db.auth.getUser();if(authError || !user)throw new LcpError('Log opnieuw in.');
    uploaded=user.id+'/'+crypto.randomUUID()+'.png';
    const result=await db.storage.from('lcp-branding').upload(uploaded,pendingLogo,{contentType:'image/png',upsert:false,cacheControl:'31536000'});
    if(result.error)throw new LcpError('Logo uploaden is niet gelukt. Controleer of de logo-opslag is geactiveerd.');
    draft.icon_url=db.storage.from('lcp-branding').getPublicUrl(uploaded).data.publicUrl;
    pushModel.validate(draft);
   }
   const {data,error}=await db.rpc('lcp_save_push_settings',{p_settings:draft,p_expected_updated_at:saved.updated_at});
   if(error)throw new LcpError(error.code==='40001'?'De instellingen zijn intussen gewijzigd. Herlaad de pagina voordat je opnieuw opslaat.':'Pushinstellingen opslaan is niet gelukt. Controleer je beheerdersrechten.');
   uploaded=null;pendingLogo=null;
   if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null;}
   fill(pushModel.normalize(data));await applyBranding(saved);
   report('Opgeslagen. Open LCP op je iPhone om de nieuwe weergave op dat apparaat op te halen. Een ander beginschermicoon kan opnieuw toevoegen aan het beginscherm vereisen.');
  } catch(error){
   if(uploaded) await db.storage.from('lcp-branding').remove([uploaded]);
   report(error instanceof LcpError?error.message:'De bewerking is niet gelukt. Controleer je verbinding en probeer opnieuw.',true);
  } finally {lock(false);}
 }
 async function selectLogo(){
  const file=el('pushLogo').files[0];if(!file)return;
  lock(true);
  try {
   if(file.type!=='image/png' || file.size<24 || file.size>2*1024*1024)throw new LcpError('Kies een PNG-bestand van maximaal 2 MB.');
   const signature=new Uint8Array(await file.slice(0,8).arrayBuffer());
   if(![137,80,78,71,13,10,26,10].every((byte,i)=>signature[i]===byte))throw new LcpError('Dit bestand is geen geldig PNG-bestand.');
   // Controleer afmetingen vóór decodering, om buitensporig grote afbeeldingen te weigeren.
   const header=new DataView(await file.slice(0,24).arrayBuffer());
   const width=header.getUint32(16),height=header.getUint32(20);
   if(!width || !height || width>4096 || height>4096)throw new LcpError('Kies een afbeelding van maximaal 4096 bij 4096 pixels.');
   const bitmap=await createImageBitmap(file);
   try {
    const canvas=document.createElement('canvas');canvas.width=512;canvas.height=512;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#ffffff';ctx.fillRect(0,0,512,512);
    const scale=Math.min(448/bitmap.width,448/bitmap.height),w=bitmap.width*scale,h=bitmap.height*scale;
    ctx.drawImage(bitmap,(512-w)/2,(512-h)/2,w,h);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(!blob)throw new LcpError('De afbeelding kon niet worden verwerkt.');
    pendingLogo=blob;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(blob);
   } finally {bitmap.close();}
   el('logoFileName').textContent=file.name;preview();report('Voorvertoning gereed. Klik op Pushinstellingen opslaan om dit logo te gebruiken.');
  } catch(error){report(error instanceof LcpError?error.message:'De bewerking is niet gelukt. Controleer je verbinding en probeer opnieuw.',true);} finally {el('pushLogo').value='';lock(false);}
 }
 el('savePush').onclick=save;
 el('pushLogo').onchange=selectLogo;
 el('chooseLogo').onclick=()=>el('pushLogo').click();
 el('resetLogo').onclick=()=>{pendingLogo=null;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=null;draftIcon=pushModel.DEFAULTS.icon_url;el('logoFileName').textContent='Standaardlogo gekozen';preview();report('Standaardlogo gekozen. Sla de pushinstellingen op om dit toe te passen.');};
 ['pushTitle','pushMessage','pushAppName','previewKind'].forEach(id=>el(id).addEventListener('input',preview));
 el('sendPushTest').onclick=async()=>{
  lock(true);try {
   if(pendingLogo)throw new LcpError('Sla het nieuwe logo eerst op voordat je een testmelding verstuurt.');
   const count=await sendPersonalTest(db,pushModel.validate(values()),message());
   report(`Testmelding aangeboden aan ${count} van je eigen geregistreerde apparaten. Controleer de ontvangst op je iPhone; aflevering is niet gegarandeerd.`);
  }catch(error){report(error instanceof LcpError?error.message:'De bewerking is niet gelukt. Controleer je verbinding en probeer opnieuw.',true);}finally{lock(false);}
 };
 fill(pushModel.normalize());
 return {load,preview,defaultMessage:()=>saved?.default_message || pushModel.DEFAULTS.default_message};
}
