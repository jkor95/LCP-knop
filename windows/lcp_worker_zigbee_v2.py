"""LCP Zigbee achtergrondworker v2.
Opstarten gebeurt via de bestaande lcp_start_jeremy.py met Windows DPAPI.
Geen tokens of wachtwoorden in deze broncode opslaan.
"""
import json
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
import requests

BASE = "https://jrlcofhpxvnlqzirjdbd.supabase.co"
TOPIC_PREFIX = "zigbee2mqtt/"
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
SYNC_SECONDS = 15
BUTTON_DEBOUNCE = 2.0
STATE_FILE = Path(r"C:\LCP\config-jeremy\sensor_state.json")

# Fallback behoudt de bestaande knop als Supabase-instellingen tijdelijk onbereikbaar zijn.
DEFAULT_BUTTON = {
    "friendly_name": "LCP_knop", "label": "LCP oproepknop",
    "device_type": "button", "enabled": True,
    "message_button": "LCP oproep (zigbee)",
}


def schedule_active(device, moment=None):
    """Bepaalt lokale Windows-tijd (zorg dat Windows op Nederlandse tijd staat)."""
    mode = device.get("arming_mode", "auto")
    if mode == "armed":
        return True
    if mode == "disarmed":
        return False
    moment = moment or datetime.now()
    day = moment.isoweekday()
    previous = 7 if day == 1 else day - 1
    now_minutes = moment.hour * 60 + moment.minute

    def minutes(hhmm):
        hours, mins = str(hhmm).split(":")
        h, m = int(hours), int(mins)
        if not 0 <= h <= 23 or not 0 <= m <= 59:
            raise ValueError("Ongeldige tijd")
        return h * 60 + m

    for period in device.get("schedule", []):
        try:
            days = {int(d) for d in period["days"]}
            start = minutes(period["start"])
            end = minutes(period["end"])
            if start == end and day in days:
                return True  # 00:00-00:00 betekent een volledige dag
            if start < end and day in days and start <= now_minutes < end:
                return True
            if start > end and (
                (day in days and now_minutes >= start)
                or (previous in days and now_minutes < end)
            ):
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


class LCPWorker:
    def __init__(self):
        self.key = os.environ["LCP_PUBLISHABLE_KEY"]
        self.email = os.environ["LCP_EMAIL"]
        self.password = os.environ["LCP_PASSWORD"]
        self.http = requests.Session()
        self.token = None
        self.expires_at = 0
        self.user_id = None
        self.devices = {"LCP_knop": dict(DEFAULT_BUTTON)}
        self.next_sync = 0
        self.events = queue.Queue(maxsize=200)
        self.last_press = {}
        self.states = self.load_states()
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def load_states(self):
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except (OSError, ValueError):
            pass
        return {}

    def save_states(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp = STATE_FILE.with_suffix(".tmp")
            temp.write_text(json.dumps(self.states, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, STATE_FILE)
        except OSError as exc:
            print("Waarschuwing: sensorstatus niet opgeslagen:", exc, flush=True)

    def login(self):
        response = self.http.post(
            BASE + "/auth/v1/token?grant_type=password",
            headers={"apikey": self.key},
            json={"email": self.email, "password": self.password},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        self.token = payload["access_token"]
        self.expires_at = time.time() + max(30, int(payload.get("expires_in", 300)) - 60)
        self.user_id = (payload.get("user") or {}).get("id")
        if not self.user_id:
            me = self.http.get(BASE + "/auth/v1/user", headers=self.headers(), timeout=15)
            me.raise_for_status()
            self.user_id = me.json()["id"]

    def headers(self):
        if not self.token or time.time() >= self.expires_at:
            self.login()
        return {
            "apikey": self.key,
            "Authorization": "Bearer " + self.token,
            "Content-Type": "application/json",
        }

    def request(self, method, path, **kwargs):
        for attempt in range(2):
            headers = self.headers()
            response = self.http.request(
                method, BASE + path, headers=headers, timeout=15, **kwargs
            )
            if response.status_code == 401 and attempt == 0:
                self.token = None
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("Supabase-aanmelding mislukt")

    def fetch_devices(self):
        response = self.request("GET", "/rest/v1/lcp_devices?select=*")
        incoming = response.json()
        if not isinstance(incoming, list):
            raise ValueError("Geen apparatenlijst ontvangen")
        settings = {}
        for entry in incoming:
            name = entry.get("friendly_name")
            if isinstance(name, str) and "/" not in name and entry.get("device_type") in ("button", "contact"):
                settings[name] = entry
        # De hardwareknop blijft werken als de instelling per ongeluk ontbreekt.
        settings.setdefault("LCP_knop", dict(DEFAULT_BUTTON))
        self.devices = settings

    def send(self, device, text):
        text = str(text or "").strip()
        if not text:
            return False
        self.request("POST", "/rest/v1/lcp_calls", json={
            "source": "zigbee",
            "message": text[:240],
            "created_by": self.user_id,
        })
        print("Oproep verzonden:", device, flush=True)
        return True

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(TOPIC_PREFIX + "+")
            print("MQTT verbonden: luister naar Zigbee-apparaten", flush=True)
        else:
            print("MQTT verbinden mislukt:", reason_code, flush=True)

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if reason_code != 0:
            print("MQTT-verbinding verbroken; automatisch opnieuw verbinden", flush=True)

    def on_message(self, client, userdata, message):
        if not message.topic.startswith(TOPIC_PREFIX):
            return
        name = message.topic[len(TOPIC_PREFIX):]
        if not name or "/" in name:
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                return
            self.events.put_nowait((name, payload, bool(message.retain)))
        except (ValueError, UnicodeError, queue.Full):
            print("Zigbee-bericht overgeslagen:", name, flush=True)

    def handle_event(self, name, data, retained):
        device = self.devices.get(name)
        if not device or not device.get("enabled", False):
            return
        if device.get("device_type") == "button":
            if retained or data.get("action") != "single":
                return
            now = time.monotonic()
            if now - self.last_press.get(name, -1e9) < BUTTON_DEBOUNCE:
                return
            self.last_press[name] = now
            self.send(name, device.get("message_button", "LCP oproep (zigbee)"))
            return

        # Zigbee2MQTT: contact=True betekent DICHT; contact=False betekent OPEN.
        if device.get("device_type") != "contact" or not isinstance(data.get("contact"), bool):
            return
        closed = data["contact"]
        previous = self.states.get(name, {})
        if previous.get("closed") is closed:
            return  # Herhaalde status is geen nieuwe opengebeurtenis.
        current = {"closed": closed, "open_at": None, "long_sent": False, "retry_after": 0}
        if not closed:
            current["open_at"] = time.time()
        self.states[name] = current
        self.save_states()
        if not closed and not retained and device.get("alert_open_when_armed", True) and schedule_active(device):
            self.send(name, device.get("message_open", "LCP – deur ongeoorloofd geopend"))

    def check_open_timers(self):
        now = time.time()
        for name, state in list(self.states.items()):
            device = self.devices.get(name)
            if not device or device.get("device_type") != "contact" or not device.get("enabled"):
                continue
            if state.get("closed") is not False or state.get("long_sent") or not device.get("alert_open_long", True):
                continue
            opened = state.get("open_at")
            if not isinstance(opened, (float, int)) or opened <= 0 or opened > now:
                continue
            minutes = max(1, int(device.get("open_limit_minutes") or 5))
            if now < opened + minutes * 60 or now < state.get("retry_after", 0):
                continue
            try:
                self.send(name, device.get("message_left_open", "LCP – deur staat te lang open"))
                state["long_sent"] = True
                self.save_states()
            except Exception as exc:
                state["retry_after"] = now + 30
                print("Waarschuwing uitgesteld; verzending mislukt:", exc, flush=True)

    def run(self):
        self.login()  # Controleer eerst Supabase-aanmelding.
        try:
            self.fetch_devices()
            print("Apparaatinstellingen geladen:", ", ".join(self.devices), flush=True)
        except Exception as exc:
            print("Instellingen tijdelijk niet bereikbaar; bestaande knop blijft werken:", exc, flush=True)
        self.next_sync = time.monotonic() + SYNC_SECONDS
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.client.loop_start()
        print("LCP achtergrondworker actief. Ctrl+C om af te sluiten.", flush=True)
        try:
            while True:
                now = time.monotonic()
                if now >= self.next_sync:
                    self.next_sync = now + SYNC_SECONDS
                    try:
                        self.fetch_devices()
                    except Exception as exc:
                        print("Instellingen synchroniseren mislukt:", exc, flush=True)
                try:
                    name, data, retained = self.events.get(timeout=0.5)
                    try:
                        self.handle_event(name, data, retained)
                    except Exception as exc:
                        print("Fout bij Zigbee-oproep:", exc, flush=True)
                except queue.Empty:
                    pass
                self.check_open_timers()
        except KeyboardInterrupt:
            pass
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            self.http.close()


if __name__ == "__main__":
    LCPWorker().run()
