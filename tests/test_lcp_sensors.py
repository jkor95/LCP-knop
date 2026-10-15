import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "windows"))
from lcp_worker_zigbee_v2 import LCPWorker, schedule_active

SCHEDULE = [
    {"days": [1, 2, 3, 4, 5], "start": "17:00", "end": "08:00"},
    {"days": [6, 7], "start": "00:00", "end": "00:00"},
]


class SensorTests(unittest.TestCase):
    def test_overnight_weekend_schedule(self):
        device = {"arming_mode": "auto", "schedule": SCHEDULE}
        self.assertTrue(schedule_active(device, datetime(2026, 10, 19, 17, 0)))
        self.assertTrue(schedule_active(device, datetime(2026, 10, 20, 7, 59)))
        self.assertFalse(schedule_active(device, datetime(2026, 10, 20, 8, 0)))
        self.assertTrue(schedule_active(device, datetime(2026, 10, 24, 12, 0)))
        self.assertTrue(schedule_active(device, datetime(2026, 10, 25, 22, 0)))

    def test_manual_override(self):
        self.assertTrue(schedule_active({"arming_mode": "armed", "schedule": []}))
        self.assertFalse(schedule_active({"arming_mode": "disarmed", "schedule": SCHEDULE}))

    def make_worker(self):
        with patch.dict(os.environ, {"LCP_PUBLISHABLE_KEY": "dummy", "LCP_EMAIL": "test@example.com", "LCP_PASSWORD": "dummy"}):
            worker = LCPWorker()
        worker.states = {}
        worker.save_states = lambda: None
        sent = []
        worker.send = lambda name, msg: sent.append((name, msg)) or True
        return worker, sent

    def test_button_text_and_debounce(self):
        worker, sent = self.make_worker()
        worker.handle_event("LCP_knop", {"action": "single"}, False)
        worker.handle_event("LCP_knop", {"action": "single"}, False)
        worker.handle_event("LCP_knop", {"action": "double"}, False)
        worker.handle_event("LCP_knop", {"action": "single"}, True)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1], "LCP oproep (zigbee)")

    def test_door_open_and_five_minute_warning_once(self):
        worker, sent = self.make_worker()
        worker.devices["LCP_deur"] = {
            "friendly_name": "LCP_deur", "device_type": "contact", "enabled": True,
            "arming_mode": "armed", "schedule": [],
            "alert_open_when_armed": True, "alert_open_long": True, "open_limit_minutes": 5,
            "message_open": "Deur geopend", "message_left_open": "Deur {minuten} minuten open",
        }
        worker.handle_event("LCP_deur", {"contact": True}, False)
        worker.handle_event("LCP_deur", {"contact": False}, False)
        self.assertEqual(sent[-1][1], "Deur geopend")
        worker.states["LCP_deur"]["open_at"] -= 301
        worker.check_open_timers()
        worker.check_open_timers()
        self.assertEqual(sent, [
            ("LCP_deur", "Deur geopend"), ("LCP_deur", "Deur 5 minuten open")
        ])
        worker.handle_event("LCP_deur", {"contact": True}, False)
        self.assertIsNone(worker.states["LCP_deur"]["open_at"])

    def test_manual_off_suppresses_open_alert_but_not_timer(self):
        worker, sent = self.make_worker()
        worker.devices["LCP_deur"] = {
            "device_type": "contact", "enabled": True, "arming_mode": "disarmed",
            "schedule": [], "alert_open_when_armed": True,
            "alert_open_long": True, "open_limit_minutes": 5,
            "message_open": "Deur geopend", "message_left_open": "Deur te lang open",
        }
        worker.handle_event("LCP_deur", {"contact": False}, False)
        self.assertEqual(sent, [])
        worker.states["LCP_deur"]["open_at"] -= 301
        worker.check_open_timers()
        self.assertEqual(sent, [("LCP_deur", "Deur te lang open")])


if __name__ == "__main__":
    unittest.main()
