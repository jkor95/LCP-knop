"""Activeer de beoordeelde LCP-uitbreiding zonder bestaande sleutels te roteren."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from supabase_inspect import request,InspectError,PROJECT,encrypt_report

ORIGINAL_HASH='6b31964126636c91cb19a40f8caaedc81daca1f8fe3602bc6b75cb0b80fc4db3'
PUBLIC_KEY='BFHyzDiGLWeWkzN2EIK6BZK4RnnUA8dknL2QCoIE95V3Ael0hNqTy88incr-d3yX6yHbVTxlIZPgdixYfUsqIIM'

def entry_source(raw):
    for match in re.finditer(br'\{"version":3,"sources":',raw):
        try:
            value,_=json.JSONDecoder().raw_decode(raw[match.start():].decode('utf-8',errors='replace'))
        except ValueError:
            continue
        for source in value.get('sourcesContent',[]):
            if source and 'webpush' in source and 'Deno.serve' in source:
                return source
    raise InspectError('De bestaande serverbron kon niet betrouwbaar worden gelezen.')

def legacy_bindings(source):
    if hashlib.sha256(source.encode()).hexdigest()!=ORIGINAL_HASH:
        raise InspectError('De bestaande pushfunctie is veranderd. Eerst opnieuw beoordelen; er wordt niets overschreven.')
    vapid=re.search(r'webpush\.setVapidDetails\(("[^"\\]*"),("[^"\\]*"),("[^"\\]*")\);',source)
    hook=re.search(r'req\.headers\.get\("x-lcp-webhook-token"\)!==("[^"\\]*")',source)
    if not vapid or not hook:raise InspectError('De bestaande bindingen zijn niet eenduidig herkenbaar.')
    subject,public,private=[json.loads(value) for value in vapid.groups()]
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    raw=base64.urlsafe_b64decode(private+'='*((4-len(private)%4)%4))
    derived=ec.derive_private_key(int.from_bytes(raw,'big'),ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    if public!=PUBLIC_KEY or base64.urlsafe_b64encode(derived).decode().rstrip('=')!=PUBLIC_KEY:
        raise InspectError('De bestaande pushsleutels passen niet bij de huidige registraties.')
    return {'VAPID_SUBJECT':subject,'VAPID_PUBLIC_KEY':public,'VAPID_PRIVATE_KEY':private,'LCP_PUSH_WEBHOOK_TOKEN':json.loads(hook[1])}

def private_json(path,value):
    with open(os.open(path,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600),'w') as file:json.dump(value,file)

def prepare(token):
    raw=request(token,'/functions/lcp-push-dispatch/body')
    source=entry_source(raw)
    current=Path('supabase/functions/lcp-push-dispatch/index.ts').read_text().strip()
    existing=json.loads(request(token,'/secrets'))
    if source.strip()==current:
        required={'VAPID_SUBJECT','VAPID_PUBLIC_KEY','VAPID_PRIVATE_KEY','LCP_PUSH_WEBHOOK_TOKEN'}
        if not required.issubset({item['name'] for item in existing}):
            raise InspectError('De bestaande activering mist geheime bindingen.')
        bindings=None  # Geen sleutels opnieuw ophalen en geen dubbele onderhoudstest.
    else:
        bindings=legacy_bindings(source)
        # Controle vóór enige mutatie; de oude live functie blijft tot de laatste deploy werken.
        for item in existing:
            if item['name'] in bindings:
                expected=hashlib.sha256(bindings[item['name']].encode()).hexdigest()
                if item.get('value')!=expected:
                    raise InspectError('Er bestaat al een afwijkende geheime binding. Deze wordt niet overschreven.')
        request(token,'/secrets',[{'name':name,'value':value} for name,value in bindings.items()])
    migration=Path('supabase/migrations/202610180001_push_settings.sql').read_text()
    request(token,'/database/query',{'query':migration})
    request(token,'/database/query',{'query':Path('supabase/migrations/202610180002_push_title_length.sql').read_text()})
    root=Path(os.environ.get('RUNNER_TEMP','/tmp'))
    private_json(root/'lcp-deployment-private.json',bindings)
    print('Bestaande sleutels veilig hergebruikt en aanvullende instellingen transactioneel geactiveerd.')

VERIFY_SQL="""load 'safeupdate';
begin;
do $$ begin
 begin
  update public.lcp_push_preferences set title=title;
  raise exception 'De bescherming tegen updates zonder WHERE is niet actief.';
 exception when cardinality_violation then null;
 end;
end $$;
rollback;
"""+Path('supabase/verify_push_settings.sql').read_text()
# De beheer-API kan de laatste resultset selecteren; bij fouten breekt de actie af.
# De testwijziging wordt altijd teruggedraaid en maakt geen oproepen aan.

def verify(token):
    checks=json.loads(request(token,'/database/query',{'query':VERIFY_SQL}))
    # Een succesvolle query inclusief ROLLBACK bewijst dat alle ingebouwde assertions slaagden.
    report={'project':PROJECT,'deployment':{'database_checks_passed':True,'safeupdate_verified':True,'database_response':checks}}
    query="""select jsonb_build_object(
      'admin_count',(select count(*) from public.lcp_members where role='admin'),
      'settings',(select jsonb_build_object('title',title,'default_message',fallback_body,'app_name',app_name,'icon_url',icon_url) from public.lcp_push_preferences),
      'subscriptions',(select coalesce(jsonb_agg(jsonb_build_object('endpoint',s.endpoint,'keys',jsonb_build_object('p256dh',s.p256dh,'auth',s.auth_secret))),'[]')
       from public.lcp_push_subscriptions s where (select count(*) from public.lcp_members where role='admin')=1
       and s.user_id=(select user_id from public.lcp_members where role='admin' limit 1)
       and s.endpoint like 'https://web.push.apple.com/%')
    ) as own_test;"""
    own=json.loads(request(token,'/database/query',{'query':query}))[0]['own_test']
    root=Path(os.environ.get('RUNNER_TEMP','/tmp'))
    bindings=json.loads((root/'lcp-deployment-private.json').read_text())
    # Alleen bij precies één beheerder wordt een persoonlijke Apple-test voorbereid.
    private_json(root/'lcp-own-push-test.json',{'bindings':bindings,'target':own})
    private_json(root/'lcp-deployment-report.json',report)
    print('Productierechten gecontroleerd; de tijdelijke testwijziging is teruggedraaid.')

def report():
    root=Path(os.environ.get('RUNNER_TEMP','/tmp'))
    value=json.loads((root/'lcp-deployment-report.json').read_text())
    value['deployment']['personal_test']=json.loads((root/'lcp-own-push-result.json').read_text())
    envelope=encrypt_report(value,Path('.github/supabase-review-public.pem').read_bytes())
    (root/'lcp-inspectie.enc.json').write_text(json.dumps(envelope))
    print('Versleuteld activeringsrapport gereed.')

def main():
    token=os.environ.get('SUPABASE_ACCESS_TOKEN','').strip()
    if not token:raise InspectError('Het GitHub-beheergeheim ontbreekt.')
    mode=sys.argv[1] if len(sys.argv)>1 else ''
    if mode=='prepare':prepare(token)
    elif mode=='verify':verify(token)
    elif mode=='report':report()
    else:raise InspectError('Ongeldige activeringsstap.')

if __name__=='__main__':
    try:main()
    except InspectError as error:print(str(error),file=sys.stderr);sys.exit(1)
    except Exception:print('Activering gestopt; gevoelige foutdetails worden niet gelogd.',file=sys.stderr);sys.exit(1)
