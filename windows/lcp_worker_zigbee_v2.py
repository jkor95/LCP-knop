"""LCP Zigbee achtergrondworker v3.
Opstarten gebeurt via de bestaande lcp_start_jeremy.py met Windows DPAPI.
Geen tokens of wachtwoorden in deze broncode opslaan.
"""
import json
import os
import queue
import threading
import time
import uuid
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path

import paho.mqtt.client as mqtt
import requests

BASE = "https://jrlcofhpxvnlqzirjdbd.supabase.co"
TOPIC_PREFIX = "zigbee2mqtt/"
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
SYNC_SECONDS = 15
BUTTON_DEBOUNCE = 2.0
WORKER_VERSION = "3.2.0"
RUNTIME_FILE = Path(__file__).with_name("lcp_sensor_runtime.json")
try:
    RUNTIME = json.loads(RUNTIME_FILE.read_text(encoding="utf-8-sig"))
except (OSError, ValueError):
    RUNTIME = {}
ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path(__file__).parent))) / "LCP" / "Werklaptop"
STATE_FILE = Path(os.environ.get("LCP_SENSOR_STATE_FILE") or RUNTIME.get("state_file") or ROOT / "sensor_state_v3.json")
HEALTH_FILE = Path(RUNTIME.get("health_file") or STATE_FILE.with_name("sensor_worker_health.json"))
MQTT_HOST = os.environ.get("LCP_MQTT_HOST", RUNTIME.get("mqtt_host", MQTT_HOST))
MQTT_PORT = int(os.environ.get("LCP_MQTT_PORT", RUNTIME.get("mqtt_port", MQTT_PORT)))
TOPIC_PREFIX = os.environ.get("LCP_MQTT_BASE_TOPIC", RUNTIME.get("topic_prefix", TOPIC_PREFIX)).rstrip("/") + "/"

# Fallback behoudt de bestaande knop als Supabase-instellingen tijdelijk onbereikbaar zijn.
DEFAULT_BUTTON = {
    "friendly_name": "LCP_knop", "label": "LCP oproepknop",
    "device_type": "button", "enabled": True,
    "message_button": "LCP oproep (zigbee)",
}


def amsterdam_time(instant=None):
    instant = instant or datetime.now(timezone.utc)
    try:
        return instant.astimezone(ZoneInfo("Europe/Amsterdam"))
    except ZoneInfoNotFoundError:
        # Windows heeft niet altijd de IANA-database. Gebruik de huidige EU-regel
        # zonder de werkende Python-omgeving met extra pakketten te wijzigen.
        year = instant.year
        march = datetime(year, 3, 31, 1, tzinfo=timezone.utc)
        october = datetime(year, 10, 31, 1, tzinfo=timezone.utc)
        start = march - timedelta(days=(march.weekday() + 1) % 7)
        end = october - timedelta(days=(october.weekday() + 1) % 7)
        return instant.astimezone(timezone(timedelta(hours=2 if start <= instant < end else 1)))


def schedule_active(device, moment=None):
    """Meldtijden in Nederland; onafhankelijk van de Windows-tijdzone."""
    mode = device.get("arming_mode", "auto")
    if mode == "armed":
        return True
    if mode == "disarmed":
        return False
    moment = moment or amsterdam_time()
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
        global STATE_FILE
        # De bestaande DPAPI-starter stelt een eigen oud statusbestand in.
        # Bewaar dat bestand; v3 krijgt bij deze installatie een apart bestand.
        if RUNTIME.get("launcher_state_isolated") is True:
            STATE_FILE = Path(RUNTIME["state_file"])
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
        self.confirmed = set()
        self.tamper_confirmed = set()
        self.open_since = {}
        self.pending = []
        self.retry_at = 0
        self.connected = False
        self.resync_needed = False
        self.connection_generation = 0
        self.availability = {}
        self.started_at = time.time()
        self.last_config_sync = 0
        self.next_health = 0
        try:
            self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:  # Behoud bestaande paho-mqtt 1.x-installaties.
            self.client = mqtt.Client()
        mqtt_user = os.environ.get("LCP_MQTT_USERNAME") or os.environ.get("MQTT_USERNAME")
        if mqtt_user:
            self.client.username_pw_set(mqtt_user, os.environ.get("LCP_MQTT_PASSWORD") or os.environ.get("MQTT_PASSWORD"))
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def load_states(self):
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {name: {"closed": value.get("closed"), "open_at": None, "long_sent": value.get("long_sent") is True, "second_sent": value.get("second_sent") is True,
                               "tamper": value.get("tamper") if isinstance(value.get("tamper"), bool) else None}
                        for name, value in raw.items() if isinstance(value, dict) and (isinstance(value.get("closed"), bool) or isinstance(value.get("tamper"), bool))}
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
        for name, device in settings.items():
            old = self.devices.get(name)
            if old is None or bool(old.get("enabled")) != bool(device.get("enabled")):
                self.invalidate(name)
            elif bool(old.get("alert_tamper")) != bool(device.get("alert_tamper")):
                self.tamper_confirmed.discard(name)
        self.devices = settings
        self.last_config_sync = time.time()

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

    def invalidate(self, name=None):
        """Na een onderbreking zijn oude statussen geen bewijs van een overgang."""
        names = [name] if name else list(self.states)
        for key in names:
            self.confirmed.discard(key)
            self.tamper_confirmed.discard(key)
            self.open_since.pop(key, None)
            if key in self.states:
                self.states[key]["open_at"] = None
        self.pending = [event for event in self.pending if name and event["name"] != name]
        if not self.pending:
            self.retry_at = 0

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            self.connection_generation += 1
            self.resync_needed = True
            client.subscribe([(TOPIC_PREFIX + "+", 0),
                              (TOPIC_PREFIX + "+/availability", 0),
                              (TOPIC_PREFIX + "bridge/state", 0)])
            print("MQTT verbonden: sensorstatus wordt opnieuw bevestigd", flush=True)
        else:
            print("MQTT verbinden mislukt:", reason_code, flush=True)

    def on_disconnect(self, client, userdata, *args):
        self.connected = False
        self.connection_generation += 1
        self.resync_needed = True
        print("MQTT-verbinding onderbroken; oude sensorstatus wordt niet herhaald", flush=True)

    def on_message(self, client, userdata, message):
        if not message.topic.startswith(TOPIC_PREFIX):
            return
        name = message.topic[len(TOPIC_PREFIX):]
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (ValueError, UnicodeError):
            payload = message.payload.decode("utf-8", errors="replace").strip()
        try:
            self.events.put_nowait((name, payload, bool(message.retain), self.connection_generation))
        except queue.Full:
            self.resync_needed = True
            print("Zigbee-wachtrij vol; sensorstatus moet opnieuw worden bevestigd", flush=True)

    def queue_sensor(self, name, kind):
        event = {"name": name, "kind": kind, "key": str(uuid.uuid4())}
        self.states[name]["last_event_key"] = event["key"]
        self.save_states()
        if len(self.pending) >= 200:
            self.invalidate(name)
            print("Sensorwachtrij vol; nieuwe uitgangsstatus vereist", flush=True)
            return
        self.pending.append(event)
        self.flush_pending()

    def flush_pending(self):
        if self.resync_needed or not self.connected or not self.pending or time.monotonic() < self.retry_at:
            return
        event = self.pending[0]
        device = self.devices.get(event["name"], {})
        if not device.get("enabled") or (event["kind"] in ("left_open", "left_open_again") and self.states.get(event["name"], {}).get("closed") is not False) or (event["kind"] == "tamper" and (not device.get("alert_tamper") or self.states.get(event["name"], {}).get("tamper") is not True)):
            self.pending.pop(0)
            return
        try:
            self.request("POST", "/rest/v1/rpc/lcp_emit_sensor_event", json={
                "p_friendly_name": event["name"], "p_kind": event["kind"], "p_event_key": event["key"],
            })
            self.pending.pop(0)
            self.retry_at = 0
            print("Sensorbericht verwerkt:", event["name"], event["kind"], flush=True)
        except requests.RequestException:
            # De server herkent dezelfde sleutel ook als de eerste HTTP-respons verloren ging.
            self.retry_at = time.monotonic() + 15
            print("Sensorbericht wacht op verbinding; dezelfde sleutel wordt opnieuw gebruikt", flush=True)

    def handle_event(self, name, data, retained):
        if self.resync_needed:
            self.resync_needed = False
            self.invalidate()
        if name == "bridge/state" or name.endswith("/availability"):
            status = data.get("state") if isinstance(data, dict) else data
            if status in ("online", "offline") and self.availability.get(name) != status:
                self.availability[name] = status
                self.invalidate(None if name == "bridge/state" else name.rsplit("/", 1)[0])
            return
        if not isinstance(data, dict) or "/" in name:
            return
        device = self.devices.get(name)
        if not device:
            return
        if device.get("device_type") == "button":
            if not device.get("enabled", False) or retained or data.get("action") != "single":
                return
            now = time.monotonic()
            if now - self.last_press.get(name, -1e9) < BUTTON_DEBOUNCE:
                return
            self.last_press[name] = now
            self.send(name, device.get("message_button", "LCP oproep (zigbee)"))
            return
        if device.get("device_type") != "contact":
            return
        if not self.connected or self.availability.get("bridge/state") == "offline" or self.availability.get(name + "/availability") == "offline":
            return
        self.handle_tamper(name, device, data, retained)
        if not isinstance(data.get("contact"), bool):
            return
        closed = data["contact"]  # Zigbee2MQTT: true=dicht, false=open.
        previous = self.states.get(name, {})
        if retained and name in self.confirmed:
            return  # Een bewaarde brokerstatus mag een recente status niet terugdraaien.
        if retained or name not in self.confirmed or not device.get("enabled"):
            # De eerste actuele status is uitsluitend een uitgangsstatus. Een bewaarde
            # openstatus start geen timer. Na herstart wordt nooit tijd teruggeteld.
            self.states.setdefault(name, {}).update({"closed": closed, "open_at": None,
                "long_sent": bool(previous.get("long_sent")) if previous.get("closed") is False and not closed else False,
                "second_sent": bool(previous.get("second_sent")) if previous.get("closed") is False and not closed else False})
            if not retained and device.get("enabled"):
                self.confirmed.add(name)
                if not closed:
                    self.open_since[name] = time.monotonic()
                    self.states[name]["open_at"] = time.time()
            else:
                self.confirmed.discard(name)
                self.open_since.pop(name, None)
            self.save_states()
            return
        if previous.get("closed") is closed:
            return
        self.states.setdefault(name, {}).update({"closed": closed, "open_at": None if closed else time.time(), "long_sent": False, "second_sent": False})
        if closed:
            self.open_since.pop(name, None)
            self.pending = [event for event in self.pending if not (event["name"] == name and event["kind"] in ("left_open", "left_open_again"))]
        else:
            self.open_since[name] = time.monotonic()
        self.save_states()
        flag = "alert_closed_when_armed" if closed else "alert_open_when_armed"
        if device.get(flag, False if closed else True) and schedule_active(device):
            self.queue_sensor(name, "closed" if closed else "opened")

    def handle_tamper(self, name, device, data, retained):
        tamper = data.get("tamper")
        if not isinstance(tamper, bool):
            return  # Een ontbrekende of onbekende status betekent niet 'veilig'.
        state = self.states.setdefault(name, {})
        previous = state.get("tamper")
        if retained and (name in self.tamper_confirmed or previous is True):
            return
        baseline = retained or name not in self.tamper_confirmed or not device.get("enabled") or not device.get("alert_tamper")
        state["tamper"] = tamper
        if baseline:
            if not retained and device.get("enabled") and device.get("alert_tamper"):
                self.tamper_confirmed.add(name)
            else:
                self.tamper_confirmed.discard(name)
        if tamper is False:
            self.pending = [event for event in self.pending if not (event["name"] == name and event["kind"] == "tamper")]
        if previous is not tamper:
            self.save_states()
        # Een eerste ACTUEEL sabotagealarm mag niet worden gemist omdat er nog
        # geen normale status was. Een bewaard alarm of reeds gemeld incident
        # wordt nooit opnieuw verstuurd, ook niet na een workerherstart.
        if not retained and device.get("enabled") and device.get("alert_tamper") and previous is not True and tamper:
            self.queue_sensor(name, "tamper")

    def check_open_timers(self):
        if not self.connected or self.resync_needed:
            return
        now = time.monotonic()
        for name, opened in list(self.open_since.items()):
            device = self.devices.get(name, {})
            state = self.states.get(name, {})
            if name not in self.confirmed or not device.get("enabled") or not device.get("alert_open_long", True):
                continue
            if state.get("closed") is not False:
                continue
            if device.get("long_alert_uses_schedule", False) and not schedule_active(device):
                continue
            minutes = max(1, min(1440, int(device.get("open_limit_minutes") or 5)))
            if not state.get("long_sent") and now - opened >= minutes * 60:
                state["long_sent"] = True
                self.save_states()
                self.queue_sensor(name, "left_open")
            second = int(device.get("second_open_limit_minutes") or 0)
            if state.get("long_sent") and not state.get("second_sent") and minutes < second <= 1440 and now - opened >= second * 60:
                state["second_sent"] = True
                self.save_states()
                self.queue_sensor(name, "left_open_again")

    def save_health(self):
        try:
            HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp = HEALTH_FILE.with_suffix(".tmp")
            temp.write_text(json.dumps({"version": WORKER_VERSION, "pid": os.getpid(),
                "started_at": self.started_at, "heartbeat": time.time(),
                "mqtt_connected": self.connected, "last_config_sync": self.last_config_sync,
                "devices": list(self.devices)}), encoding="utf-8")
            os.replace(temp, HEALTH_FILE)
        except OSError:
            print("Statusbestand kon niet worden bijgewerkt", flush=True)

    def acquire_lock(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = STATE_FILE.with_suffix(".lock").open("a+b")
        self.lock_file.write(b"0")
        self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            print("Er draait al een LCP-worker voor deze installatie; tweede start overgeslagen", flush=True)
            return False
        return True

    def run(self):
        if not self.acquire_lock():
            return
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
                if self.resync_needed:
                    self.resync_needed = False
                    self.invalidate()
                try:
                    name, data, retained, generation = self.events.get(timeout=0.5)
                    if generation != self.connection_generation:
                        continue
                    try:
                        self.handle_event(name, data, retained)
                    except Exception as exc:
                        print("Fout bij Zigbee-oproep:", exc, flush=True)
                except queue.Empty:
                    pass
                # Verwerk reeds ontvangen sluitingen vóór een timer kan afgaan.
                if self.events.empty():
                    self.check_open_timers()
                self.flush_pending()
                if time.monotonic() >= self.next_health:
                    self.next_health = time.monotonic() + 5
                    self.save_health()
        except KeyboardInterrupt:
            pass
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            self.http.close()
            self.lock_file.close()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        print("LCP sensorworker " + WORKER_VERSION + ": Python en MQTT-onderdelen beschikbaar")
    else:
        LCPWorker().run()
