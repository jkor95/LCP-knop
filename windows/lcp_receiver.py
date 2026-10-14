"""LCP Windows 11 ontvanger: gebruikerssessie, geen browser nodig."""
import getpass, json, os, sys, time, threading
from pathlib import Path
import requests, keyring
from winotify import Notification, audio
import pystray
from PIL import Image, ImageDraw

BASE="https://jrlcofhpxvnlqzirjdbd.supabase.co"
KEY="sb_publishable_l-rXo1gmk9dGQ2QogsUexw_bAZfd84R"
APP="LCP Knop"
ROOT=Path(os.environ["LOCALAPPDATA"])/"LCPKnop"
ROOT.mkdir(parents=True,exist_ok=True)
CFG=ROOT/"settings.json"
STOP=threading.Event()
state={"status":"Starten...","last":None,"session":None,"expires":0,"user":None}
def settings():
    return json.loads(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}
def configure():
    email=input("Supabase e-mailadres: ").strip()
    password=getpass.getpass("Supabase wachtwoord (niet zichtbaar): ")
    token=authenticate(email,password)
    keyring.set_password(APP,email,password)
    CFG.write_text(json.dumps({"email":email}),encoding="utf-8")
    print("Account gecontroleerd. Wachtwoord veilig opgeslagen via Windows Credential Manager.")
def authenticate(email,password):
    r=requests.post(BASE+"/auth/v1/token?grant_type=password",headers={"apikey":KEY},json={"email":email,"password":password},timeout=20)
    r.raise_for_status()
    return r.json()
def headers():
    if time.time()>state["expires"]:
        conf=settings()
        password=keyring.get_password(APP,conf["email"])
        if not password: raise RuntimeError("Geen wachtwoord gevonden: voer --setup uit")
        token=authenticate(conf["email"],password)
        state["session"]=token["access_token"]
        state["expires"]=time.time()+token.get("expires_in",3600)-90
    return {"apikey":KEY,"Authorization":"Bearer "+state["session"]}
def request(method,path,**kw):
    h=headers()
    r=requests.request(method,BASE+path,headers=h,timeout=20,**kw)
    if r.status_code==401:
        state["expires"]=0
        h=headers()
        r=requests.request(method,BASE+path,headers=h,timeout=20,**kw)
    r.raise_for_status()
    return r
def notify(title,message):
    toast=Notification(app_id=APP,title=title,msg=message,duration="long")
    toast.set_audio(audio.Default,loop=False)
    toast.show()
def poll():
    while not STOP.is_set():
        try:
            data=request("GET","/rest/v1/lcp_calls",params={"select":"id,message,created_at","order":"created_at.desc","limit":"20"}).json()
            ids=[c["id"] for c in data]
            if state["last"] is None:
                state["last"]=set(ids)
            else:
                new=[c for c in reversed(data) if c["id"] not in state["last"]]
                state["last"]=set(ids)
                for call in new: notify("LCP oproep",call.get("message") or "Nieuwe oproep")
            state["status"]="Verbonden"
        except Exception as e:
            state["status"]="Verbindingsfout: "+str(e)[:80]
        STOP.wait(5)
def test_local(icon,item):
    try: notify("LCP testmelding","Windows-ontvanger werkt zonder Edge")
    except Exception as e: state["status"]="Meldingsfout: "+str(e)[:80]
def send_test(icon,item):
    def job():
        try:
            uid=request("GET","/auth/v1/user").json()["id"]
            request("POST","/rest/v1/lcp_calls",json={"source":"windows","message":"LCP Windows-testoproep","created_by":uid})
            state["status"]="Testoproep verstuurd"
        except Exception as e: state["status"]="Versturen mislukt: "+str(e)[:80]
    threading.Thread(target=job,daemon=True).start()
def quit_app(icon,item):
    STOP.set()
    icon.stop()
def icon_image():
    img=Image.new("RGB",(64,64),"#16704e")
    d=ImageDraw.Draw(img)
    d.ellipse((15,10,49,44),fill="white")
    d.rectangle((23,43,41,51),fill="white")
    return img
def main():
    if "--setup" in sys.argv:
        configure()
        return
    if not settings().get("email"):
        print("Eerst configureren: python lcp_receiver.py --setup")
        return
    threading.Thread(target=poll,daemon=True).start()
    tray=pystray.Icon("LCP Knop",icon_image(),"LCP Knop",menu=pystray.Menu(
        pystray.MenuItem(lambda item: "Status: "+state["status"],lambda icon,item:None,enabled=False),
        pystray.MenuItem("Test Windows-melding",test_local),
        pystray.MenuItem("Verstuur testoproep",send_test),
        pystray.MenuItem("Afsluiten",quit_app)))
    tray.run()
if __name__=="__main__": main()
