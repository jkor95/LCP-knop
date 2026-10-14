"""LCP keyboard/test worker. Run as a user-session background task (not Windows service)."""
import os,time,requests
from pynput import keyboard
BASE='https://jrlcofhpxvnlqzirjdbd.supabase.co'
KEY=os.environ['LCP_PUBLISHABLE_KEY']
EMAIL=os.environ['LCP_EMAIL']
PASSWORD=os.environ['LCP_PASSWORD']
def login():
 r=requests.post(BASE+'/auth/v1/token?grant_type=password',headers={'apikey':KEY},json={'email':EMAIL,'password':PASSWORD},timeout=15);r.raise_for_status();return r.json()
session=login()
def send(source):
 global session
 if time.time()>session.get('_expires',0):
  session=login();session['_expires']=time.time()+session.get('expires_in',300)-60
 headers={'apikey':KEY,'Authorization':'Bearer '+session['access_token'],'Content-Type':'application/json'}
 me=requests.get(BASE+'/auth/v1/user',headers=headers,timeout=15);me.raise_for_status()
 r=requests.post(BASE+'/rest/v1/lcp_calls',headers=headers,json={'source':source,'message':'LCP oproep ('+source+')','created_by':me.json()['id']},timeout=15);r.raise_for_status()
 print('Oproep verzonden:',source,flush=True)
session['_expires']=time.time()+session.get('expires_in',300)-60
def pressed(k):
 if k==keyboard.Key.f9:
  try:send('keyboard')
  except Exception as e:print('Fout:',e,flush=True)
print('LCP actief: druk F9 voor een testoproep. Ctrl+C om af te sluiten.',flush=True)
with keyboard.Listener(on_press=pressed) as listener:listener.join()
