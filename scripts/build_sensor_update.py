"""Bouw een lokaal controleerbaar Windows-pakket zonder geheimen of downloads."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=['Update-LCP-Deursensoren.ps1','Update-LCP-Deursensoren.cmd','Herstel-LCP-Worker.cmd','Controleer-LCP-Start.ps1','Controleer-LCP-Start.cmd','Controleer-LCP-Deursensoren.cmd','inspect_lcp_launcher.py','lcp_worker_zigbee_v2.py','check_lcp_installation.py']

def build():
    files={name:(ROOT/'windows'/name).read_bytes() for name in FILES}
    files['LEESMIJ.md']=(ROOT/'windows/README_deursensoren.md').read_bytes()
    files['manifest.json']=json.dumps({'version':'3.1.0','files':{name:hashlib.sha256(files[name]).hexdigest() for name in ['lcp_worker_zigbee_v2.py','check_lcp_installation.py']}},indent=2).encode()
    target=ROOT/'downloads/LCP-deursensor-update.zip'
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,23,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    print('Windows-updatepakket gebouwd:',target.name)

if __name__=='__main__':build()
