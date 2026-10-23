import importlib.util
import json
import hashlib
import zipfile
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('install_check',ROOT/'windows/check_lcp_installation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class InstallationTests(unittest.TestCase):
    def test_download_package_matches_reviewed_sources(self):
        with zipfile.ZipFile(ROOT/'downloads/LCP-deursensor-update.zip') as package:
            manifest=json.loads(package.read('manifest.json'))
            for name,digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256(package.read(name)).hexdigest(),digest)
            for name in ['lcp_worker_zigbee_v2.py','check_lcp_installation.py','Update-LCP-Deursensoren.ps1','Update-LCP-Deursensoren.cmd','Herstel-LCP-Worker.cmd','Controleer-LCP-Start.ps1','Controleer-LCP-Start.cmd','Controleer-LCP-Deursensoren.cmd','inspect_lcp_launcher.py']:
                self.assertEqual(package.read(name),(ROOT/'windows'/name).read_bytes())

    def test_preserves_existing_broker_and_topic_without_running_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            worker=Path(folder)/'worker.py'
            worker.write_text("import paho.mqtt.client as mqtt\nimport os\nMQTT_HOST='localhost'\nMQTT_PORT=1884\nTOPIC_PREFIX='school/lcp/'\na=os.environ['LCP_EMAIL'];b=os.environ['LCP_PASSWORD'];c=os.environ['LCP_PUBLISHABLE_KEY']\nraise RuntimeError('mag niet draaien')\n")
            self.assertEqual(module.inspect_worker(worker),{'mqtt_host':'localhost','mqtt_port':1884,'topic_prefix':'school/lcp/'})
    def test_unknown_credentials_or_dynamic_broker_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            worker=Path(folder)/'worker.py'
            for text in ['import paho.mqtt.client as mqtt\nsecret="niet tonen"',
                         "import paho.mqtt.client as mqtt\nMQTT_HOST=custom_config()\na=['LCP_EMAIL','LCP_PASSWORD','LCP_PUBLISHABLE_KEY']"]:
                worker.write_text(text)
                with self.assertRaises(ValueError) as error:module.inspect_worker(worker)
                self.assertNotIn('niet tonen',str(error.exception))
    def test_repository_v2_and_v3_are_recognized_with_existing_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            worker=Path(folder)/'worker.py'
            worker.write_bytes((ROOT/'windows/lcp_worker_zigbee_v2.py').read_bytes())
            (Path(folder)/'lcp_sensor_runtime.json').write_text(json.dumps({'mqtt_host':'localhost','mqtt_port':1889,'topic_prefix':'custom/'}))
            self.assertEqual(module.inspect_worker(worker)['mqtt_port'],1889)

if __name__=='__main__':unittest.main()
