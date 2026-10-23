import copy
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows'))
from lcp_worker_zigbee_v2 import LCPWorker, schedule_active, amsterdam_time
from zoneinfo import ZoneInfoNotFoundError

SCHEDULE = [
    {'days': [1, 2, 3, 4, 5], 'start': '17:00', 'end': '08:00'},
    {'days': [6, 7], 'start': '00:00', 'end': '00:00'},
]

class SensorTests(unittest.TestCase):
    def test_tamper_payload_without_contact_alerts_once_per_incident_24_7(self):
        worker,sent=self.make_worker()
        worker.devices['LCP nooddeur'].update(alert_tamper=True,arming_mode='disarmed')
        worker.handle_event('LCP nooddeur',{'tamper':False},False)
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        worker.handle_event('LCP nooddeur',{'battery':80},False)
        worker.handle_event('LCP nooddeur',{'tamper':'false'},False)
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        self.assertEqual(self.kinds(sent),['tamper'])
        worker.handle_event('LCP nooddeur',{'tamper':False},False)
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        self.assertEqual(self.kinds(sent),['tamper','tamper'])
        self.assertNotEqual(sent[0]['p_event_key'],sent[1]['p_event_key'])

    def test_retained_startup_and_reconnect_tamper_are_only_baselines(self):
        worker,sent=self.make_worker()
        worker.devices['LCP nooddeur']['alert_tamper']=True
        worker.handle_event('LCP nooddeur',{'tamper':True},True)
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        worker.invalidate()
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        self.assertEqual(self.kinds(sent),[])
        worker.handle_event('LCP nooddeur',{'tamper':False},False)
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        worker.handle_event('LCP nooddeur',{'tamper':False},True)
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        self.assertEqual(self.kinds(sent),['tamper'])

    def test_tamper_does_not_reset_door_or_open_timers(self):
        worker,sent=self.make_worker()
        worker.devices['LCP nooddeur'].update(alert_tamper=True,second_open_limit_minutes=10)
        worker.handle_event('LCP nooddeur',{'contact':True,'tamper':False},False)
        self.event(worker,False)
        worker.handle_event('LCP nooddeur',{'tamper':True},False)
        self.now+=300
        worker.check_open_timers()
        self.now+=300
        worker.check_open_timers()
        self.event(worker,True)
        worker.handle_event('LCP nooddeur',{'contact':True,'tamper':True},False)
        self.assertEqual(self.kinds(sent),['opened','tamper','left_open','left_open_again','closed'])
        self.assertTrue(worker.states['LCP nooddeur']['tamper'])

    def test_disabled_tamper_and_reserve_never_notify(self):
        for enabled,alert in [(False,True),(True,False)]:
            with self.subTest(enabled=enabled,alert=alert):
                worker,sent=self.make_worker()
                worker.devices['LCP nooddeur'].update(enabled=enabled,alert_tamper=alert)
                for value in [False,True,False,True]:
                    worker.handle_event('LCP nooddeur',{'tamper':value},False)
                self.assertEqual(self.kinds(sent),[])

    def test_tamper_only_state_is_persisted_and_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'state.json'
            with patch('lcp_worker_zigbee_v2.STATE_FILE',file):
                worker,_=self.make_worker()
                worker.devices['LCP nooddeur']['alert_tamper']=True
                worker.handle_event('LCP nooddeur',{'tamper':False},False)
                LCPWorker.save_states(worker)
                loaded=LCPWorker.load_states(worker)
                self.assertFalse(loaded['LCP nooddeur']['tamper'])
                self.assertIsNone(loaded['LCP nooddeur']['closed'])

    def test_second_warning_at_ten_minutes_once_and_close_cancels_both(self):
        worker,sent=self.make_worker()
        worker.devices['LCP nooddeur']['second_open_limit_minutes']=10
        self.event(worker,True)
        self.event(worker,False)
        self.now+=300
        worker.check_open_timers()
        self.now+=299
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent),['opened','left_open'])
        self.now+=1
        worker.check_open_timers()
        self.now+=3600
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent),['opened','left_open','left_open_again'])
        self.event(worker,True)
        self.event(worker,False)
        self.now+=300
        worker.check_open_timers()
        self.event(worker,True)
        self.now+=600
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent),['opened','left_open','left_open_again','closed','opened','left_open','closed'])

    def test_second_warning_not_repeated_after_reconnect_same_open_cycle(self):
        worker,sent=self.make_worker()
        worker.devices['LCP nooddeur']['second_open_limit_minutes']=10
        self.event(worker,False)
        self.now+=600
        worker.check_open_timers()
        worker.invalidate()
        self.event(worker,False)
        self.now+=600
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent),['left_open','left_open_again'])

    def test_old_launcher_state_file_is_preserved_with_dedicated_v3_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Path(folder)/'old.json';new=Path(folder)/'v3.json'
            old.write_text('{"oud":"bewaren"}')
            with patch('lcp_worker_zigbee_v2.STATE_FILE',old), patch('lcp_worker_zigbee_v2.RUNTIME',{'launcher_state_isolated':True,'state_file':str(new)}):
                worker,_=self.make_worker()
                LCPWorker.save_states(worker)
            self.assertEqual(old.read_text(),'{"oud":"bewaren"}')
            self.assertTrue(new.is_file())

    def setUp(self):
        self.now = 1000.0
        self.clock = patch('lcp_worker_zigbee_v2.time.monotonic', side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def make_worker(self):
        with patch.dict(os.environ, {'LCP_PUBLISHABLE_KEY': 'dummy', 'LCP_EMAIL': 'test@example.com', 'LCP_PASSWORD': 'dummy'}):
            worker = LCPWorker()
        worker.states = {}
        worker.save_states = lambda: None
        worker.connected = True
        sent = []
        worker.send = lambda name, msg: sent.append({'button': name, 'message': msg}) or True
        worker.request = lambda method, path, **kw: sent.append(kw['json']) or object()
        worker.devices['LCP nooddeur'] = {
            'friendly_name': 'LCP nooddeur', 'device_type': 'contact', 'enabled': True,
            'arming_mode': 'armed', 'schedule': [], 'alert_open_when_armed': True,
            'alert_closed_when_armed': True, 'alert_open_long': True,
            'long_alert_uses_schedule': True, 'open_limit_minutes': 5,
        }
        return worker, sent

    def event(self, worker, closed, retained=False):
        worker.handle_event('LCP nooddeur', {'contact': closed}, retained)

    def kinds(self, sent):
        return [x['p_kind'] for x in sent if 'p_kind' in x]

    def test_overnight_weekend_schedule(self):
        device = {'arming_mode': 'auto', 'schedule': SCHEDULE}
        self.assertTrue(schedule_active(device, datetime(2026, 10, 19, 17, 0)))
        self.assertTrue(schedule_active(device, datetime(2026, 10, 20, 7, 59)))
        self.assertFalse(schedule_active(device, datetime(2026, 10, 20, 8, 0)))
        self.assertTrue(schedule_active(device, datetime(2026, 10, 24, 12, 0)))

    def test_windows_without_timezone_database_uses_correct_dutch_dst(self):
        with patch('lcp_worker_zigbee_v2.ZoneInfo',side_effect=ZoneInfoNotFoundError):
            summer=amsterdam_time(datetime(2026,10,25,0,59,tzinfo=timezone.utc))
            winter=amsterdam_time(datetime(2026,10,25,1,0,tzinfo=timezone.utc))
            self.assertEqual(summer.isoformat(),'2026-10-25T02:59:00+02:00')
            self.assertEqual(winter.isoformat(),'2026-10-25T02:00:00+01:00')

    def test_reconnect_during_wait_invalidates_before_status_is_processed(self):
        worker,sent=self.make_worker()
        self.event(worker,True)
        worker.resync_needed=True
        self.event(worker,False)
        self.assertEqual(sent,[])
        self.assertIn('LCP nooddeur',worker.confirmed)
        worker.handle_event('LCP nooddeur/availability',{'state':'offline'},False)
        self.event(worker,True)
        self.assertFalse(worker.states['LCP nooddeur']['closed'])

    def test_second_worker_cannot_start_for_same_installation(self):
        first,_=self.make_worker()
        second,_=self.make_worker()
        with tempfile.TemporaryDirectory() as folder, patch('lcp_worker_zigbee_v2.STATE_FILE',Path(folder)/'state.json'):
            try:
                self.assertTrue(first.acquire_lock())
                self.assertFalse(second.acquire_lock())
            finally:
                first.lock_file.close()

    def test_manual_override(self):
        self.assertTrue(schedule_active({'arming_mode': 'armed', 'schedule': []}))
        self.assertFalse(schedule_active({'arming_mode': 'disarmed', 'schedule': SCHEDULE}))

    def test_button_text_debounce_retained_and_double_unchanged(self):
        worker, sent = self.make_worker()
        worker.handle_event('LCP_knop', {'action': 'single'}, False)
        worker.handle_event('LCP_knop', {'action': 'single'}, False)
        worker.handle_event('LCP_knop', {'action': 'double'}, False)
        worker.handle_event('LCP_knop', {'action': 'single'}, True)
        self.assertEqual(sent, [{'button': 'LCP_knop', 'message': 'LCP oproep (zigbee)'}])
        self.now += 3
        worker.handle_event('LCP_knop', {'action': 'single'}, False)
        self.assertEqual(len(sent), 2)

    def test_open_close_and_exact_five_minute_warning_once(self):
        worker, sent = self.make_worker()
        self.event(worker, True)
        self.assertEqual(sent, [])
        self.event(worker, False)
        self.now += 299
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent), ['opened'])
        self.now += 1
        worker.check_open_timers()
        worker.check_open_timers()
        self.event(worker, True)
        self.now += 1000
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent), ['opened', 'left_open', 'closed'])
        self.assertNotIn('LCP nooddeur', worker.open_since)

    def test_close_before_deadline_cancels_warning(self):
        worker, sent = self.make_worker()
        self.event(worker, True)
        self.event(worker, False)
        self.now += 299
        self.event(worker, True)
        self.now += 1000
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent), ['opened', 'closed'])

    def test_identical_states_and_battery_reports_do_not_duplicate_or_restart_timer(self):
        worker, sent = self.make_worker()
        self.event(worker, True)
        self.event(worker, False)
        self.now += 250
        for _ in range(10):
            self.event(worker, False)
            worker.handle_event('LCP nooddeur', {'battery': 90}, False)
        self.now += 50
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent), ['opened', 'left_open'])

    def test_retained_status_never_alerts_or_starts_timer(self):
        worker, sent = self.make_worker()
        self.event(worker, False, retained=True)
        self.now += 900
        worker.check_open_timers()
        self.assertEqual(sent, [])
        self.event(worker, False)
        self.now += 299
        worker.check_open_timers()
        self.assertEqual(sent, [])
        self.now += 1
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent), ['left_open'])
        self.event(worker, True, retained=True)
        self.assertFalse(worker.states['LCP nooddeur']['closed'])

    def test_restart_does_not_alert_from_opposite_persisted_state(self):
        worker, sent = self.make_worker()
        worker.states['LCP nooddeur'] = {'closed': False, 'open_at': 1, 'long_sent': False}
        self.event(worker, True)
        worker.check_open_timers()
        self.assertEqual(sent, [])
        self.event(worker, False)
        self.assertEqual(self.kinds(sent), ['opened'])

    def test_restart_does_not_backdate_timer_or_repeat_delivered_warning(self):
        worker, sent = self.make_worker()
        worker.states['LCP nooddeur'] = {'closed': False, 'open_at': 1, 'long_sent': False}
        self.event(worker, False)
        worker.check_open_timers()
        self.assertEqual(sent, [])
        self.now += 300
        worker.check_open_timers()
        restart, again = self.make_worker()
        restart.states = copy.deepcopy(worker.states)
        self.event(restart, False)
        self.now += 600
        restart.check_open_timers()
        self.assertEqual(again, [])
        self.event(restart, True)
        self.event(restart, False)
        self.now += 300
        restart.check_open_timers()
        self.assertEqual(self.kinds(again), ['closed', 'opened', 'left_open'])

    def test_mqtt_or_zigbee_interruption_requires_fresh_baseline(self):
        for interruption in ['mqtt', 'zigbee']:
            with self.subTest(interruption=interruption):
                worker, sent = self.make_worker()
                self.event(worker, True)
                self.event(worker, False)
                if interruption == 'mqtt':
                    worker.on_disconnect(None, None, 1)
                    worker.invalidate()
                    self.now += 600
                    worker.check_open_timers()
                    worker.connected = True
                else:
                    worker.handle_event('LCP nooddeur/availability', {'state': 'offline'}, False)
                    self.now += 600
                    worker.check_open_timers()
                    worker.handle_event('LCP nooddeur/availability', {'state': 'online'}, False)
                self.event(worker, True)
                self.assertEqual(self.kinds(sent), ['opened'])
                self.event(worker, False)
                self.assertEqual(self.kinds(sent), ['opened', 'opened'])

    def test_reserve_and_individual_flags(self):
        worker, sent = self.make_worker()
        door = worker.devices['LCP nooddeur']
        door['enabled'] = False
        self.event(worker, True)
        self.event(worker, False)
        self.now += 600
        worker.check_open_timers()
        self.assertEqual(sent, [])
        door['enabled'] = True
        door['alert_closed_when_armed'] = False
        door['alert_open_long'] = False
        self.event(worker, True)
        self.event(worker, False)
        self.now += 600
        worker.check_open_timers()
        self.event(worker, True)
        self.assertEqual(self.kinds(sent), ['opened'])

    def test_optional_schedule_and_legacy_independent_timer(self):
        worker, sent = self.make_worker()
        door = worker.devices['LCP nooddeur']
        door['arming_mode'] = 'disarmed'
        self.event(worker, True)
        self.event(worker, False)
        self.now += 301
        worker.check_open_timers()
        self.assertEqual(sent, [])
        door['long_alert_uses_schedule'] = False
        worker.check_open_timers()
        self.assertEqual(self.kinds(sent), ['left_open'])

    def test_retry_after_lost_http_response_reuses_event_key(self):
        worker, sent = self.make_worker()
        self.event(worker, True)
        attempts = []
        def request(method, path, **kw):
            attempts.append(kw['json'])
            if len(attempts) == 1:
                raise requests.Timeout('antwoord verloren')
        worker.request = request
        self.event(worker, False)
        self.event(worker, False)
        self.now += 15
        worker.flush_pending()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]['p_event_key'], attempts[1]['p_event_key'])
        self.assertEqual(worker.pending, [])

if __name__ == '__main__':
    unittest.main()
