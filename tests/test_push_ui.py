"""Echte Chromium-tests met nagebootste Supabase; er worden geen oproepen verstuurd.
LCP_BROWSER_TESTS=1 python -m unittest discover -s tests -p test_push_ui.py -v
Vereist playwright en Chromium (CHROMIUM_PATH of Playwright-installatie).
"""
import functools
import http.server
import os
from pathlib import Path
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.environ.get('LCP_BROWSER_TESTS') == '1', 'Optionele browsertests: stel LCP_BROWSER_TESTS=1 in')
class PushUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args): pass
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(permissions=['notifications'])
        self.context.route('https://esm.sh/**', lambda route: route.fulfill(path=str(ROOT/'tests/fixtures/supabase.js'), content_type='application/javascript', headers={'Access-Control-Allow-Origin':'*'}))
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def open_settings(self):
        self.page.goto(self.base+'/settings.html')
        self.page.wait_for_selector('#form', state='visible')
        self.page.wait_for_function("document.querySelector('#label').value === 'Bestaande knop'")

    def test_save_preferences_preserves_devices_and_registrations(self):
        self.open_settings()
        self.assertEqual(self.page.input_value('#pushTitle'), 'Bestaande titel')
        self.assertEqual(self.page.input_value('#message_button'), 'Bestaande knoptekst')
        self.page.fill('#pushTitle', 'LCP – Receptie')
        self.page.fill('#pushMessage', 'Er wacht iemand bij de receptie.')
        self.page.fill('#pushAppName', 'LCP')
        self.page.click('#savePush')
        self.page.wait_for_function("document.querySelector('#pushStatus').textContent.startsWith('Opgeslagen.')")
        self.assertEqual(self.page.text_content('#previewTitle'), 'LCP – Receptie')
        events = self.page.evaluate('window.__lcpTest.events')
        saves = [e for e in events if e.get('rpc') == 'lcp_save_push_settings']
        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0]['args']['p_expected_updated_at'], '2026-10-18T09:00:00Z')
        self.assertFalse(any(e.get('operation') in ('insert','update','delete','upsert') for e in events))

    def test_device_preview_and_new_device_default(self):
        self.open_settings()
        self.page.select_option('#previewKind', 'message_button')
        self.assertEqual(self.page.text_content('#previewBody'), 'Bestaande knoptekst')
        self.page.select_option('#deviceSelect', '1')
        self.page.select_option('#previewKind', 'message_left_open')
        self.assertEqual(self.page.text_content('#previewBody'), 'Achterdeur 5 minuten open')
        self.assertEqual(self.page.input_value('#arming_mode'), 'armed')
        self.assertEqual(self.page.locator('.schedule-row').count(), 1)
        self.page.click('#newButton')
        self.assertEqual(self.page.input_value('#message_button'), 'Bestaande standaardtekst')

    def test_second_door_warning_preview_validation_and_save(self):
        self.open_settings()
        self.page.select_option('#deviceSelect','1')
        self.page.fill('#second_open_limit_minutes','10')
        self.page.fill('#message_second_open','Let op: al {minuten} minuten open.')
        self.page.select_option('#previewKind','message_second_open')
        self.assertEqual(self.page.text_content('#previewBody'),'Let op: al 10 minuten open.')
        self.page.fill('#second_open_limit_minutes','4')
        self.page.click('#save')
        self.assertIn('later zijn dan de eerste',self.page.text_content('#error'))
        self.page.fill('#second_open_limit_minutes','10')
        self.page.click('#save')
        self.page.wait_for_function("window.__lcpTest.events.some(e=>e.operation==='update' && e.table==='lcp_devices')")
        row=self.page.evaluate("window.__lcpTest.events.find(e=>e.operation==='update' && e.table==='lcp_devices').row")
        self.assertEqual(row['second_open_limit_minutes'],10)
        self.assertEqual(row['message_second_open'],'Let op: al {minuten} minuten open.')

    def test_save_error_identifies_cause_and_preserves_draft(self):
        self.open_settings()
        self.page.fill('#pushTitle', 'Mijn nieuwe titel')
        for code,expected in [('42501','beheerdersaccount'),('22023','afgekeurd'),('40001','intussen gewijzigd'),('PGRST301','sessie is verlopen'),('23514','serverfout')]:
            self.page.evaluate("code=>{window.__saveError={code,message:'private server details'};}", code)
            self.page.click('#savePush')
            self.page.wait_for_function("code=>document.querySelector('#pushStatus').textContent.includes('foutcode '+code)", arg=code)
            status=self.page.text_content('#pushStatus')
            self.assertIn(expected,status)
            self.assertNotIn('private server details',status)
            self.assertEqual(self.page.input_value('#pushTitle'),'Mijn nieuwe titel')
            self.assertFalse(self.page.locator('#savePush').is_disabled())
        self.page.evaluate('window.__saveError=null')
        self.page.click('#savePush')
        self.page.wait_for_function("document.querySelector('#pushStatus').textContent.startsWith('Opgeslagen.')")

    def test_png_upload_reset_and_personal_test(self):
        self.open_settings()
        self.page.set_input_files('#pushLogo', {'name':'logo.png','mimeType':'image/png','buffer':(ROOT/'icon-192.png').read_bytes()})
        self.page.wait_for_function("document.querySelector('#pushStatus').textContent.startsWith('Voorvertoning gereed')")
        self.assertTrue(self.page.get_attribute('#logoPreview','src').startswith('blob:'))
        self.page.click('#savePush')
        self.page.wait_for_function("document.querySelector('#pushStatus').textContent.startsWith('Opgeslagen.')")
        event = self.page.evaluate("window.__lcpTest.events.find(e=>e.upload)")
        self.assertEqual(event['type'], 'image/png')
        self.assertTrue(event['upload'].endswith('.png'))
        self.page.click('#sendPushTest')
        self.page.wait_for_function("document.querySelector('#pushStatus').textContent.startsWith('Testmelding aangeboden')")
        events = self.page.evaluate('window.__lcpTest.events')
        test = next(e for e in events if e.get('invoke'))
        self.assertEqual(test['invoke'], 'lcp-push-test')
        self.assertEqual(set(test['args']['body']), {'settings','message'})
        self.assertFalse(any(e.get('table') == 'lcp_calls' for e in events))
        self.page.click('#resetLogo')
        self.assertEqual(self.page.get_attribute('#logoPreview','src'),'./icon-512.png')

    def test_door_close_message_and_individual_options_are_saved(self):
        self.open_settings()
        self.page.select_option('#deviceSelect','1')
        self.assertTrue(self.page.is_checked('#alert_closed_when_armed'))
        self.assertEqual(self.page.input_value('#message_closed'),'Achterdeur gesloten')
        self.page.select_option('#previewKind','message_closed')
        self.assertEqual(self.page.text_content('#previewBody'),'Achterdeur gesloten')
        self.page.fill('#message_closed','De nooddeur is weer dicht.')
        self.page.uncheck('#alert_open_when_armed')
        self.page.fill('#open_limit_minutes','8')
        self.page.select_option('#arming_mode','armed')
        self.page.click('#save')
        self.page.wait_for_function("window.__lcpTest.events.some(e=>e.operation==='update' && e.table==='lcp_devices')")
        row=self.page.evaluate("window.__lcpTest.events.find(e=>e.operation==='update' && e.table==='lcp_devices').row")
        self.assertEqual(row['friendly_name'],'LCP_deur')
        self.assertEqual(row['message_closed'],'De nooddeur is weer dicht.')
        self.assertTrue(row['alert_closed_when_armed'])
        self.assertTrue(row['long_alert_uses_schedule'])
        self.assertFalse(row['alert_open_when_armed'])
        self.assertEqual(row['open_limit_minutes'],8)
        self.assertEqual(row['arming_mode'],'armed')

    def test_invalid_logo_is_not_uploaded(self):
        self.open_settings()
        self.page.set_input_files('#pushLogo', {'name':'fake.png','mimeType':'image/png','buffer':b'<svg><script>evil()</script></svg>'})
        self.page.wait_for_function("document.querySelector('#pushStatus').textContent.includes('geen geldig PNG')")
        self.assertFalse(self.page.evaluate('window.__lcpTest.events.some(e=>e.upload)'))

    def test_non_admin_cannot_open_settings(self):
        self.page.add_init_script("window.__role='viewer'")
        self.page.goto(self.base+'/settings.html')
        self.page.wait_for_function("document.querySelector('#notauthorized').textContent.includes('Alleen LCP-beheerders')")
        self.assertFalse(self.page.locator('#form').is_visible())
        self.assertFalse(self.page.evaluate("window.__lcpTest.events.some(e=>e.rpc)"))

    def test_missing_backend_does_not_break_device_settings(self):
        self.page.add_init_script('window.__missingSettings=true')
        self.open_settings()
        self.assertTrue(self.page.locator('#savePush').is_disabled())
        self.assertFalse(self.page.locator('#save').is_disabled())
        self.assertIn('nog niet geactiveerd', self.page.text_content('#pushStatus'))
        self.assertEqual(self.page.input_value('#message_button'), 'Bestaande knoptekst')

    def test_app_personal_test_and_alarm_controls(self):
        self.page.goto(self.base+'/app.html')
        self.page.wait_for_selector('#app', state='visible')
        self.page.click('#test')
        self.page.wait_for_function("document.querySelector('#pushstatus').textContent.startsWith('Testmelding aangeboden')")
        self.assertFalse(self.page.evaluate("window.__lcpTest.events.some(e=>e.table==='lcp_calls' && e.operation!=='select')"))
        self.page.check('#soundenabled')
        self.page.fill('#soundvolume', '45')
        self.page.click('#soundactivate')
        self.page.wait_for_function("document.querySelector('#soundstatus').textContent.startsWith('Geluid geactiveerd')")
        preferences = self.page.evaluate("JSON.parse(localStorage.getItem('lcp_alarm_preferences_v1'))")
        self.assertEqual(preferences['volume'], 45)
        self.assertTrue(preferences['enabled'])

    def test_viewer_can_receive_but_has_no_test_button(self):
        self.page.add_init_script("window.__role='viewer'")
        self.page.goto(self.base+'/app.html')
        self.page.wait_for_selector('#app', state='visible')
        self.assertFalse(self.page.locator('#test').is_visible())
        self.assertTrue(self.page.locator('#permission').is_visible())
        self.assertFalse(self.page.locator('#resetHistory').is_visible())

    def test_history_reset_preserves_calls_and_new_calls_appear(self):
        self.page.add_init_script("window.__calls=[{id:1,message:'Oude oproep',source:'zigbee',created_at:'2026-10-18T00:01:00Z'}]")
        self.page.goto(self.base+'/app.html')
        self.page.wait_for_selector('.call')
        self.page.click('#resetHistory')
        self.page.wait_for_function("document.querySelector('#historyStatus').textContent.includes('voor iedereen gereset')")
        self.assertEqual(self.page.locator('.call').count(),0)
        self.assertEqual(self.page.evaluate('window.__lcpTest.calls.length'),1)
        self.page.evaluate("window.__lcpTest.calls.unshift({id:2,message:'Nieuwe oproep',source:'zigbee',created_at:new Date(Date.now()+1000).toISOString()})")
        self.page.click('#refresh')
        self.page.wait_for_selector('.call')
        self.assertIn('Nieuwe oproep',self.page.text_content('#calls'))
        self.assertNotIn('Oude oproep',self.page.text_content('#calls'))
        self.assertFalse(self.page.evaluate("window.__lcpTest.events.some(e=>e.operation==='delete')"))

    def test_open_app_refreshes_week_boundary_without_new_call(self):
        self.page.clock.install()
        self.page.add_init_script("window.__calls=[{id:1,message:'Vorige week',source:'zigbee',created_at:'2026-10-18T00:01:00Z'}]")
        self.page.goto(self.base+'/app.html')
        self.page.wait_for_selector('.call')
        self.page.evaluate("window.__historySince='2026-10-25T00:00:00Z'")
        self.page.clock.fast_forward(8100)
        self.page.wait_for_function("document.querySelectorAll('.call').length===0")
        self.assertIn('Geen oproepen',self.page.text_content('#calls'))

    def test_reset_failure_preserves_visible_history(self):
        self.page.add_init_script("window.__resetError=true;window.__calls=[{id:1,message:'Bestaande oproep',source:'zigbee',created_at:'2026-10-18T00:01:00Z'}]")
        self.page.goto(self.base+'/app.html')
        self.page.wait_for_selector('.call')
        self.page.click('#resetHistory')
        self.page.wait_for_function("document.querySelector('#historyStatus').textContent.includes('ingelogde beheerder')")
        self.assertIn('Bestaande oproep',self.page.text_content('#calls'))
        self.assertFalse(self.page.locator('#resetHistory').is_disabled())

    def test_real_serviceworker_persists_branding_and_serves_manifest(self):
        self.open_settings()
        self.page.wait_for_function('navigator.serviceWorker.controller !== null')
        self.page.fill('#pushTitle', 'LCP – Nieuwe titel')
        self.page.fill('#pushAppName', 'LCP Receptie')
        self.page.click('#savePush')
        self.page.wait_for_function("document.querySelector('#pushStatus').textContent.startsWith('Opgeslagen.')")
        manifest = self.page.evaluate("fetch('./manifest.webmanifest?branding=test').then(r=>r.json())")
        self.assertEqual(manifest['short_name'], 'LCP Receptie')
        self.assertEqual(manifest['id'], self.base+'/app.html')
        worker = self.context.service_workers[0]
        saved = worker.evaluate('branding()')
        self.assertEqual(saved['title'], 'LCP – Nieuwe titel')
        self.assertEqual(manifest['icons'][0]['sizes'], '512x512')
        # De echte push-eventhandler gebruikt dezelfde opgeslagen voorkeuren.
        result = worker.evaluate("""async()=>{
          let result;
          self.registration.showNotification=async(title,options)=>{result={title,options};};
          let completion;
          const event=new Event('push');
          event.data={json:()=>({id:123,message:'Knop ingedrukt'})};
          event.waitUntil=promise=>{completion=promise;};
          self.dispatchEvent(event);await completion;return result;
        }""")
        self.assertEqual(result['title'], 'LCP – Nieuwe titel')
        self.assertEqual(result['options']['body'], 'Knop ingedrukt')
        self.assertEqual(result['options']['data']['url'], './app.html')

if __name__ == '__main__': unittest.main()
