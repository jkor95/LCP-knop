import {LcpError} from './push-client.js?v=20261018-3';

export async function readCallHistory(db) {
 const {data:state,error:stateError}=await db.rpc('lcp_get_call_history_state');
 if(stateError || !state?.since || !Number.isFinite(Date.parse(state.since)))
  throw new LcpError('De oproepgeschiedenis kon niet worden geladen. Ververs de pagina en probeer opnieuw.');
 // De bestaande SELECT-rechten en RLS op oproepen blijven gelden.
 const {data,error}=await db.from('lcp_calls').select('id,source,message,created_at,acknowledged_at')
  .gte('created_at',state.since).order('created_at',{ascending:false}).limit(40);
 if(error)throw new LcpError('De oproepgeschiedenis kon niet worden geladen. Controleer je verbinding en probeer opnieuw.');
 return data || [];
}

export async function resetCallHistory(db) {
 const {error}=await db.rpc('lcp_reset_call_history');
 if(error)throw new LcpError(error.code==='42501'
  ?'Alleen een ingelogde beheerder mag de oproepgeschiedenis resetten.'
  :'De oproepgeschiedenis is niet gereset. Probeer het opnieuw.');
}
