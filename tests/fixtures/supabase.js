// Alleen gebruikt door browsertests; deze module wordt nooit door de app geladen.
export function createClient(){
 const state=window.__lcpTest={events:[],settings:{title:'Bestaande titel',default_message:'Bestaande standaardtekst',app_name:'LCP',icon_url:'./icon-512.png',updated_at:'2026-10-18T09:00:00Z'}};
 const devices=[{id:'button',label:'Bestaande knop',friendly_name:'LCP_knop',device_type:'button',enabled:true,message_button:'Bestaande knoptekst',message_open:'Deur geopend',message_left_open:'Deur {minuten} minuten open',open_limit_minutes:5,arming_mode:'auto',schedule:[]},
 {id:'door',label:'Achterdeur',friendly_name:'LCP_deur',device_type:'contact',enabled:true,message_button:'Oproep',message_open:'Achterdeur geopend',message_left_open:'Achterdeur {minuten} minuten open',alert_open_when_armed:true,alert_open_long:true,open_limit_minutes:5,arming_mode:'armed',schedule:[{days:[1,2,3,4,5],start:'17:00',end:'08:00'}]}];
 return {
  auth:{getUser:async()=>({data:{user:window.__noUser?null:{id:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'}}}),signOut:async()=>{},signInWithPassword:async()=>({error:null})},
  from(table){const q={table,operation:'select'};return {
   select(){return this;},eq(){return this;},order(){return this;},limit(){return this;},is(){return this;},
   insert(row){q.operation='insert';q.row=row;state.events.push(q);return this;},update(row){q.operation='update';q.row=row;state.events.push(q);return this;},delete(){q.operation='delete';state.events.push(q);return this;},upsert(row){q.operation='upsert';state.events.push(q);return this;},
   single:async()=>table==='lcp_members'?{data:{role:window.__role || 'admin'}}:{data:{id:'button'}},
   then(resolve){return Promise.resolve(table==='lcp_devices'?{data:devices}:{data:[]}).then(resolve);}
  };},
  async rpc(name,args){
   state.events.push({rpc:name,args});
   if(window.__missingSettings)return {error:{code:'PGRST202'}};
   if(name==='lcp_save_push_settings' && window.__saveError)return {error:window.__saveError};
   if(name==='lcp_save_push_settings')state.settings={...args.p_settings,updated_at:'2026-10-18T10:00:00Z'};
   return {data:state.settings};
  },
  storage:{from(){return {
   async upload(path,blob,options){state.events.push({upload:path,type:blob.type,size:blob.size,options});return {data:{path}};},
   getPublicUrl(path){return {data:{publicUrl:'https://jrlcofhpxvnlqzirjdbd.supabase.co/storage/v1/object/public/lcp-branding/'+path}};},
   async remove(paths){state.events.push({remove:paths});return {};},
  };}},
  functions:{async invoke(name,args){state.events.push({invoke:name,args});return {data:{sent:1}};}},
  channel(){return {on(){return this;},subscribe(fn){fn('SUBSCRIBED');return this;}};},removeChannel:async()=>{},
 };
}
