"""Activeer uitsluitend de beoordeelde deursensoruitbreiding in het bestaande project."""
import json
import os
from pathlib import Path
import sys
from supabase_inspect import request,encrypt_report,InspectError,PROJECT

def main():
    token=os.environ.get('SUPABASE_ACCESS_TOKEN','').strip()
    if not token:raise InspectError('Het GitHub-beheergeheim ontbreekt.')
    before=json.loads(request(token,'/database/query',{'query':"select jsonb_agg(to_jsonb(d)-array['alert_closed_when_armed','message_closed','long_alert_uses_schedule'] order by id) as devices from public.lcp_devices d"}))
    request(token,'/database/query',{'query':Path('supabase/migrations/202610230001_door_sensors.sql').read_text()})
    checks=json.loads(request(token,'/database/query',{'query':Path('supabase/verify_door_sensors.sql').read_text()}))
    after=json.loads(request(token,'/database/query',{'query':"select friendly_name,label,enabled,alert_open_when_armed,alert_closed_when_armed,alert_open_long,long_alert_uses_schedule,open_limit_minutes,arming_mode from public.lcp_devices where friendly_name in('LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve') order by friendly_name"}))
    report={'project':PROJECT,'sensors':{'checks':checks,'devices':after,'existing_devices_backup':before,'no_test_push_sent':True}}
    output=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'lcp-inspectie.enc.json'
    output.write_text(json.dumps(encrypt_report(report,Path('.github/supabase-review-public.pem').read_bytes())))
    print('Vier deursensoren geactiveerd; bestaande instellingen en knopkoppeling behouden. Geen testmelding verstuurd.')

if __name__=='__main__':
    try:main()
    except InspectError as error:print(str(error),file=sys.stderr);sys.exit(1)
    except Exception:print('Sensoractivering gestopt; gevoelige foutdetails worden niet gelogd.',file=sys.stderr);sys.exit(1)
