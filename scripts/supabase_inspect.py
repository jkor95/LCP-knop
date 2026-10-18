"""Alleen-lezen projectcontrole via GitHub Actions; rapport is versleuteld.
Het toegangstoken wordt uitsluitend uit de procesomgeving gebruikt.
"""
import base64
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime,timedelta,timezone

PROJECT = 'jrlcofhpxvnlqzirjdbd'
API = 'https://api.supabase.com/v1/projects/' + PROJECT
AUDIT_SQL = """
select jsonb_build_object(
 'columns',(select coalesce(jsonb_agg(to_jsonb(c)),'[]') from
  (select table_name,column_name,data_type,is_nullable,column_default
   from information_schema.columns where table_schema='public'
   and table_name in('lcp_push_preferences','lcp_members','lcp_push_subscriptions','lcp_calls','lcp_devices')
   order by table_name,ordinal_position) c),
 'policies',(select coalesce(jsonb_agg(to_jsonb(p)),'[]') from pg_policies p
  where (schemaname='public' and tablename in('lcp_push_preferences','lcp_members','lcp_push_subscriptions','lcp_calls','lcp_devices'))
  or (schemaname='storage' and tablename='objects')),
 'rls',(select coalesce(jsonb_agg(jsonb_build_object('table',relname,'enabled',relrowsecurity,'forced',relforcerowsecurity)),'[]')
  from pg_class where relnamespace='public'::regnamespace and relname like 'lcp_%'),
 'preferences',(select coalesce(jsonb_agg(to_jsonb(p)),'[]') from
  (select * from public.lcp_push_preferences limit 100) p),
 'preference_count',(select count(*) from public.lcp_push_preferences),
 'registrations',(select coalesce(jsonb_agg(to_jsonb(s)),'[]') from
   (select case when endpoint like 'https://web.push.apple.com/%' then 'Apple' else 'Ander platform' end as platform,
    count(*) as aantal,min(created_at) as oudste,max(created_at) as nieuwste
    from public.lcp_push_subscriptions group by 1) s),
 'member_roles',(select coalesce(jsonb_agg(to_jsonb(m)),'[]') from (select role,count(*) as aantal from public.lcp_members group by role) m),
 'buckets',(select coalesce(jsonb_agg(to_jsonb(b)),'[]') from
  (select id,name,public,file_size_limit,allowed_mime_types from storage.buckets where id='lcp-branding') b),
 'triggers',(select coalesce(jsonb_agg(jsonb_build_object('name',tgname,'definition',pg_get_triggerdef(oid))),'[]')
  from pg_trigger where tgrelid='public.lcp_calls'::regclass and not tgisinternal),
 'functions',(select coalesce(jsonb_agg(jsonb_build_object('name',proname,'definition',pg_get_functiondef(oid))),'[]')
  from pg_proc where pronamespace='public'::regnamespace and prokind='f' and proname ~ '(lcp|push|notify)')
) as audit;
"""

class InspectError(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Het beheertoken mag nooit naar een redirectbestemming worden gestuurd.
        return None

def request(token, path, payload=None):
    if not path.startswith('/') or '..' in path or '://' in path:
        raise InspectError('Ongeldig beheerpad.')
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API+path, data=data, headers={
        'Authorization':'Bearer '+token, 'Content-Type':'application/json',
        'User-Agent':'LCP-projectcontrole/1.0',
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=45) as response:
            body = response.read(16*1024*1024+1)
            if len(body)>16*1024*1024:
                raise InspectError('Het projectantwoord is te groot voor deze controle.')
            return body
    except urllib.error.HTTPError as error:
        # Alleen een versleutelde diagnose; nooit API-antwoorden of credentials loggen.
        if os.environ.get('GITHUB_ACTIONS')=='true':
            try:
                diagnostic={'project':PROJECT,'api_error':{'status':error.code,'path':path,'response_base64':base64.b64encode(error.read(2*1024*1024)).decode()}}
                envelope=encrypt_report(diagnostic,Path('.github/supabase-review-public.pem').read_bytes())
                (Path(os.environ['RUNNER_TEMP'])/'lcp-inspectie.enc.json').write_text(json.dumps(envelope))
            except Exception:
                pass
        raise InspectError('Supabase-beheeraanvraag geweigerd (HTTP '+str(error.code)+').') from None
    except urllib.error.URLError:
        raise InspectError('Verbinding met de Supabase-beheer-API mislukt.') from None

def collect(token,include_sources=True):
    report = {'project':PROJECT}
    report['database'] = json.loads(request(token,'/database/query',{'query':AUDIT_SQL}))
    functions = json.loads(request(token,'/functions'))
    if not isinstance(functions,list):
        raise InspectError('Onverwacht antwoord op de lijst met serverfuncties.')
    report['functions'] = functions
    report['secret_names'] = [item['name'] for item in json.loads(request(token,'/secrets'))]
    report['sources'] = {}
    for function in (functions if include_sources else []):
        slug = function.get('slug','')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',slug):
            raise InspectError('Onverwachte naam van een serverfunctie.')
        if not re.search(r'(lcp|push|notify)',slug,re.I):
            continue
        try:
            raw = request(token,'/functions/'+slug+'/body')
            report['sources'][slug] = {'body_base64':base64.b64encode(raw).decode()}
        except InspectError as error:
            # Overige controles blijven bruikbaar als de API geen broncode levert.
            report['sources'][slug] = {'error':str(error)}
    if not include_sources:
        end=datetime.now(timezone.utc);start=end-timedelta(minutes=20)
        params=urllib.parse.urlencode({'sql':'select timestamp,event_message from function_edge_logs order by timestamp desc limit 30','iso_timestamp_start':start.isoformat(),'iso_timestamp_end':end.isoformat()})
        try:report['delivery_logs']=json.loads(request(token,'/analytics/endpoints/logs.all?'+params))
        except InspectError as error:report['delivery_logs']={'error':str(error)}
    return report

def encrypt_report(report, public_key):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aad = ('LCP-Supabase-inspectie-v1:'+PROJECT).encode()
    encrypted = AESGCM(key).encrypt(nonce,json.dumps(report,ensure_ascii=False).encode(),aad)
    wrapped = serialization.load_pem_public_key(public_key).encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    enc = lambda value:base64.b64encode(value).decode()
    return {'version':1,'project':PROJECT,'key':enc(wrapped),'nonce':enc(nonce),'ciphertext':enc(encrypted)}

def main():
    token = os.environ.get('SUPABASE_ACCESS_TOKEN','').strip()
    if not token:
        raise InspectError('Voeg eerst het GitHub Actions-geheim SUPABASE_ACCESS_TOKEN toe.')
    public_key = Path('.github/supabase-review-public.pem').read_bytes()
    envelope = encrypt_report(collect(token,include_sources=os.environ.get('INCLUDE_SOURCE','true')=='true'),public_key)
    output = Path(os.environ.get('RUNNER_TEMP','/tmp'))/'lcp-inspectie.enc.json'
    output.write_text(json.dumps(envelope),encoding='utf-8')
    print('Projectcontrole voltooid. Het rapport is versleuteld; er zijn geen appinstellingen gewijzigd.')

if __name__ == '__main__':
    try:
        main()
    except InspectError as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('Projectcontrole afgebroken. Er worden geen gevoelige foutgegevens gelogd.',file=sys.stderr)
        sys.exit(1)
