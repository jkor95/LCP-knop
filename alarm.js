// Origineel LCP-alarm: een korte oplopende alarmreeks, met zachte afbouw.
// Werkt alleen wanneer de webapp draait en afspelen door de browser is toegestaan.
const PREF_KEY = "lcp_alarm_preferences_v1";

function preferences() {
  try {
    const saved = JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
    const volume = Number(saved.volume);
    return {
      enabled: saved.enabled === true,
      volume: Number.isFinite(volume) ? Math.max(0, Math.min(100, volume)) : 70,
    };
  } catch {
    return { enabled: false, volume: 70 };
  }
}

export function createLcpAlarm() {
  let prefs = preferences();
  let ctx = null;
  let armed = false;
  let lastSoundAt = -Infinity;

  const store = () => {
    try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch {}
  };
  const context = () => {
    const Constructor = window.AudioContext || window.webkitAudioContext;
    if (!Constructor) throw new Error("Deze browser ondersteunt geen Web Audio.");
    if (!ctx || ctx.state === "closed") ctx = new Constructor();
    return ctx;
  };

  function play({ preview = false } = {}) {
    if (!preview && (!prefs.enabled || !armed)) return false;
    if (prefs.volume === 0) return false;
    if (!ctx || ctx.state !== "running") return false;

    // Maximaal één automatisch alarm per 2,5 seconden; test mag altijd.
    const now = performance.now();
    if (!preview && now - lastSoundAt < 2500) return false;
    lastSoundAt = now;

    const t = ctx.currentTime + 0.015;
    const level = Math.min(0.22, (prefs.volume / 100) * 0.19);

    // Oplopend signaal, korte rust en een duidelijke dubbele eindtoon.
    const notes = [
      [0.00, 587.33, 0.13], [0.20, 783.99, 0.13],
      [0.40, 987.77, 0.19], [0.80, 783.99, 0.17],
      [1.03, 987.77, 0.35],
    ];
    for (const [offset, frequency, duration] of notes) {
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(frequency, t + offset);
      gain.gain.setValueAtTime(0.0001, t + offset);
      gain.gain.linearRampToValueAtTime(level, t + offset + 0.018);
      gain.gain.setValueAtTime(level, t + offset + Math.max(0.022, duration - 0.060));
      gain.gain.exponentialRampToValueAtTime(0.0001, t + offset + duration);
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.onended = () => {
        oscillator.disconnect();
        gain.disconnect();
      };
      oscillator.start(t + offset);
      oscillator.stop(t + offset + duration + 0.015);
    }
    return true;
  }

  // Moet worden aangeroepen na een echte tik/klik: iOS blokkeert anders audio.
  async function activate({ preview = true } = {}) {
    if (ctx && ctx.state === "running") {
      armed = true;
      if (preview) play({ preview: true });
      return true;
    }
    const audio = context();
    await audio.resume();
    if (audio.state !== "running") throw new Error("Audio is nog geblokkeerd door de browser.");
    armed = true;
    if (preview) play({ preview: true });
    return true;
  }

  function setEnabled(value) {
    prefs.enabled = !!value;
    store();
  }
  function setVolume(value) {
    const n = Number(value);
    prefs.volume = Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 70;
    store();
  }
  return {
    get enabled() { return prefs.enabled; },
    get volume() { return prefs.volume; },
    get armed() { return armed && ctx?.state === "running"; },
    setEnabled, setVolume, activate, play,
  };
}
