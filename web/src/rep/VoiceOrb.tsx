import { useEffect, useRef, useState } from "react";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import { RecorderError, WavRecorder } from "../recorder";

interface Props {
  onRecorded: (wav: Blob) => void;
  onError: (message: string) => void;
  working?: boolean;
  disabled?: boolean;
}

const BARS = 30;
const TAP_MS = 450; // a press shorter than this toggles recording; a longer press is push-to-talk

const clock = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/**
 * The main voice control. Tap to start and tap/stop to finish (with pause), or press and hold to talk
 * and release to send. The waveform follows the real microphone level.
 */
export function VoiceOrb({ onRecorded, onError, working, disabled }: Props) {
  const { t } = useI18n();
  const recorder = useRef<WavRecorder | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const bars = useRef<number[]>(Array(BARS).fill(0.08));
  const barEls = useRef<(HTMLElement | null)[]>([]);
  const starting = useRef(false);
  const downAt = useRef(0);
  const releasedHeld = useRef<number | null>(null);
  const mode = useRef<"pending" | "toggle" | "hold">("pending");
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [holdMode, setHoldMode] = useState(false);
  const [opening, setOpening] = useState(false);

  useEffect(() => () => recorder.current?.cancel(), []);

  useEffect(() => {
    if (!recording) return;
    const timer = setInterval(() => setSeconds(recorder.current?.seconds ?? 0), 100);
    return () => clearInterval(timer);
  }, [recording]);

  function onLevel(level: number) {
    root.current?.style.setProperty("--lvl", level.toFixed(3));
    bars.current.push(Math.max(0.08, level));
    bars.current.shift();
    barEls.current.forEach((el, i) => { if (el) el.style.transform = `scaleY(${bars.current[i]})`; });
  }

  function resetMeter() {
    root.current?.style.setProperty("--lvl", "0");
    bars.current = Array(BARS).fill(0.08);
    barEls.current.forEach((el) => { if (el) el.style.transform = "scaleY(.08)"; });
  }

  async function finish() {
    const rec = recorder.current;
    if (!rec || !rec.recording) return;
    recorder.current = null;
    setRecording(false); setPaused(false);
    resetMeter();
    try {
      onRecorded(await rec.stop());
      navigator.vibrate?.(10);
    } catch (error) {
      onError(error instanceof RecorderError ? error.message : "Recording failed.");
    }
  }

  function settle(held: number) {
    if (held < TAP_MS) mode.current = "toggle"; else { mode.current = "hold"; setHoldMode(true); void finish(); }
  }

  async function begin(event?: React.PointerEvent) {
    if (disabled || working || starting.current) return;
    if (recorder.current?.recording) { if (mode.current === "toggle") void finish(); return; }
    event?.currentTarget.setPointerCapture?.(event.pointerId);
    starting.current = true;
    downAt.current = performance.now();
    releasedHeld.current = event ? null : 0; // keyboard: behaves like a tap
    mode.current = "pending";
    setHoldMode(false);
    const rec = new WavRecorder();
    recorder.current = rec;
    setOpening(true);
    try {
      await rec.start(onLevel, () => void finish());
      setRecording(true); setPaused(false); setSeconds(0);
      navigator.vibrate?.(18);
      if (releasedHeld.current !== null) settle(releasedHeld.current);
    } catch (error) {
      recorder.current = null;
      onError(error instanceof RecorderError ? error.message : "Could not start recording.");
    } finally {
      starting.current = false;
      setOpening(false);
    }
  }

  function release() {
    const held = performance.now() - downAt.current;
    if (starting.current) { releasedHeld.current = held; return; }
    if (recorder.current?.recording && mode.current === "pending") settle(held);
  }

  function togglePause() {
    const rec = recorder.current;
    if (!rec) return;
    if (rec.isPaused) { rec.resume(); setPaused(false); } else { rec.pause(); setPaused(true); }
  }

  return (
    <div ref={root} className={`vorb ${opening ? "is-opening" : ""} ${recording ? "is-rec" : ""} ${paused ? "is-paused" : ""} ${working ? "is-working" : ""}`}>
      <div className="vorb-stage">
        <span className="vorb-ring" />
        <button
          type="button" className="vorb-btn" disabled={disabled || working}
          aria-label={recording ? "Stop recording" : t("tapToRecord")}
          onPointerDown={begin} onPointerUp={release} onPointerCancel={release}
          onContextMenu={(e) => e.preventDefault()}
          onKeyDown={(e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); void begin(); } }}
        >
          {working ? <span className="vorb-spin" /> : <Icon name="mic" size={76} stroke={1.5} />}
        </button>
      </div>

      <div className="vorb-wave" aria-hidden>
        {Array.from({ length: BARS }, (_, i) => <i key={i} ref={(el) => { barEls.current[i] = el; }} />)}
      </div>

      {recording ? (
        <>
          <div className="vorb-time" aria-live="off">{clock(seconds)}</div>
          <div className="vorb-ctrl">
            <button type="button" className="vorb-pause" onClick={togglePause} aria-label={paused ? "Resume" : "Pause"}>
              <Icon name={paused ? "play" : "pause"} size={22} stroke={2.6} />
            </button>
            <button type="button" className="vorb-stop" onClick={() => void finish()} aria-label="Stop and send"><i /></button>
          </div>
          <small className="vorb-hint">{holdMode ? t("release") : paused ? "Paused" : t("recording")}</small>
        </>
      ) : opening ? (
        <div className="vorb-idle"><b>Starting…</b><small>Allow the microphone if asked</small></div>
      ) : !working ? (
        <div className="vorb-idle"><b>{t("tapToRecord")}</b><small>{t("orHold")}</small></div>
      ) : null}
    </div>
  );
}
