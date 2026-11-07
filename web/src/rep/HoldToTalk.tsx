import { useEffect, useRef, useState } from "react";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import { RecorderError, WavRecorder } from "../recorder";

interface Props {
  onRecorded: (wav: Blob) => void;
  onError: (message: string) => void;
  label?: string;
  disabled?: boolean;
}

const BARS = 24;

/** Compact press-and-hold control used for spoken corrections. */
export function HoldToTalk({ onRecorded, onError, label, disabled }: Props) {
  const { t } = useI18n();
  const recorder = useRef<WavRecorder | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const bars = useRef<number[]>(Array(BARS).fill(0.08));
  const barEls = useRef<(HTMLElement | null)[]>([]);
  const [holding, setHolding] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const starting = useRef(false);
  const wantStop = useRef(false);

  useEffect(() => () => recorder.current?.cancel(), []);

  useEffect(() => {
    if (!holding) return;
    const timer = setInterval(() => setSeconds(recorder.current?.seconds ?? 0), 100);
    return () => clearInterval(timer);
  }, [holding]);

  function onLevel(level: number) {
    bars.current.push(Math.max(0.08, level));
    bars.current.shift();
    barEls.current.forEach((el, i) => { if (el) el.style.transform = `scaleY(${bars.current[i]})`; });
  }

  async function begin(event?: React.PointerEvent) {
    if (disabled || starting.current || holding) return;
    event?.currentTarget.setPointerCapture?.(event.pointerId);
    starting.current = true;
    wantStop.current = false;
    const rec = new WavRecorder();
    recorder.current = rec;
    try {
      await rec.start(onLevel, () => void finish());
      setHolding(true); setSeconds(0);
      navigator.vibrate?.(18);
      if (wantStop.current) await finish();
    } catch (error) {
      recorder.current = null;
      onError(error instanceof RecorderError ? error.message : "Could not start recording.");
    } finally {
      starting.current = false;
    }
  }

  async function finish() {
    wantStop.current = true;
    const rec = recorder.current;
    if (!rec || !rec.recording) return;
    recorder.current = null;
    setHolding(false);
    bars.current = Array(BARS).fill(0.08);
    barEls.current.forEach((el) => { if (el) el.style.transform = "scaleY(.08)"; });
    try {
      onRecorded(await rec.stop());
      navigator.vibrate?.(10);
    } catch (error) {
      onError(error instanceof RecorderError ? error.message : "Recording failed.");
    }
  }

  return (
    <div ref={root} className={`vbar ${holding ? "is-live" : ""}`}>
      <button
        type="button" className="vbar-btn" disabled={disabled} aria-label={label ?? t("correct")}
        onPointerDown={begin} onPointerUp={() => void finish()} onPointerCancel={() => void finish()}
        onContextMenu={(e) => e.preventDefault()}
        onKeyDown={(e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) void begin(); }}
        onKeyUp={(e) => { if (e.key === " " || e.key === "Enter") void finish(); }}
      >
        <span className="vbar-icon"><Icon name="mic" size={18} stroke={2.2} /></span>
        <span className="vbar-wave" aria-hidden>
          {Array.from({ length: BARS }, (_, i) => <i key={i} ref={(el) => { barEls.current[i] = el; }} />)}
        </span>
        <span className="vbar-text">{holding ? `${seconds.toFixed(1)}s · ${t("release")}` : label ?? t("correct")}</span>
      </button>
    </div>
  );
}
