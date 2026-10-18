"""Publiceer uitsluitend een versleuteld rapport op een afzonderlijke beheerbranch."""
import base64
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

REPO='jkor95/LCP-knop'
BRANCH='lcp-supabase-rapport'
FILENAME='lcp-inspectie.enc.json'
class PublishError(Exception):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def main():
    token=os.environ['GH_TOKEN']
    sha=os.environ['REPORT_BASE_SHA']
    path=Path(os.environ.get('RUNNER_TEMP','/tmp'))/FILENAME
    content=path.read_bytes();envelope=json.loads(content)
    if set(envelope)!={'version','project','key','nonce','ciphertext'} or envelope['project']!='jrlcofhpxvnlqzirjdbd':
        raise PublishError('Alleen het versleutelde LCP-rapport mag worden gepubliceerd.')
    for key in ['key','nonce','ciphertext']:base64.b64decode(envelope[key],validate=True)
    def api(path,method='GET',payload=None,allow404=False):
        request=urllib.request.Request('https://api.github.com/repos/'+REPO+path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json'},method=method)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:return json.load(response)
        except urllib.error.HTTPError as error:
            if allow404 and error.code==404:return None
            raise PublishError('GitHub weigert rapportopslag (HTTP '+str(error.code)+').') from None
    if api('/git/ref/heads/'+BRANCH,allow404=True) is None:
        api('/git/refs','POST',{'ref':'refs/heads/'+BRANCH,'sha':sha})
    existing=api('/contents/'+FILENAME+'?ref='+BRANCH,allow404=True)
    payload={'message':'Werk versleutelde Supabase-inspectie bij','branch':BRANCH,'content':base64.b64encode(content).decode()}
    if existing:payload['sha']=existing['sha']
    api('/contents/'+FILENAME,'PUT',payload)
    print('Versleuteld rapport opgeslagen op de afzonderlijke beheerbranch; main is ongewijzigd.')

if __name__=='__main__':
    try:main()
    except PublishError as error:print(str(error),file=sys.stderr);sys.exit(1)
    except Exception:print('Rapportopslag mislukt; gevoelige foutdetails worden niet gelogd.',file=sys.stderr);sys.exit(1)
