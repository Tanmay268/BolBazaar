import { useEffect, useRef, useState } from "react";
import { Icon } from "../Icon";
import { useI18n } from "../i18n";
import { RecorderError, WavRecorder } from "../recorder";

interface Props {
  onRecorded: (wav: Blob) => void;
  onError: (message: string) => void;
  /** "orb" is the main hero control; "bar" is the compact inline control used for corrections. */
  variant?: "orb" | "bar";
  label?: string;
  disabled?: boolean;
  working?: boolean;
}

const BARS = 24;

/**
 * Press-and-hold voice control. The rings and bars follow the real microphone level
 * (written straight to CSS variables so a 60 fps meter doesn't re-render React).
 */
export function HoldToTalk({ onRecorded, onError, variant = "orb", label, disabled, working }: Props) {
  const { t } = useI18n();
  const recorder = useRef<WavRecorder | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const bars = useRef<number[]>(Array(BARS).fill(0.06));
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
    root.current?.style.setProperty("--lvl", level.toFixed(3));
    bars.current.push(Math.max(0.06, level));
    bars.current.shift();
    barEls.current.forEach((el, i) => { if (el) el.style.transform = `scaleY(${bars.current[i]})`; });
  }

  function resetMeter() {
    root.current?.style.setProperty("--lvl", "0");
    bars.current = Array(BARS).fill(0.06);
    barEls.current.forEach((el) => { if (el) el.style.transform = "scaleY(.06)"; });
  }

  async function begin(event?: React.PointerEvent) {
    if (disabled || working || starting.current || holding) return;
    event?.currentTarget.setPointerCapture?.(event.pointerId);
    starting.current = true;
    wantStop.current = false;
    const rec = new WavRecorder();
    recorder.current = rec;
    try {
      await rec.start(onLevel, () => void finish());
      setHolding(true);
      setSeconds(0);
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
    resetMeter();
    try {
      onRecorded(await rec.stop());
      navigator.vibrate?.(10);
    } catch (error) {
      onError(error instanceof RecorderError ? error.message : "Recording failed.");
    }
  }

  const handlers = {
    onPointerDown: begin,
    onPointerUp: () => void finish(),
    onPointerCancel: () => void finish(),
    onContextMenu: (e: React.SyntheticEvent) => e.preventDefault(),
    onKeyDown: (e: React.KeyboardEvent) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) void begin(); },
    onKeyUp: (e: React.KeyboardEvent) => { if (e.key === " " || e.key === "Enter") void finish(); },
  };

  if (variant === "bar") {
    return (
      <div ref={root} className={`vbar ${holding ? "is-live" : ""}`}>
        <button type="button" className="vbar-btn" disabled={disabled || working} aria-label={label ?? t("correct")} {...handlers}>
          <span className="vbar-icon"><Icon name="mic" size={18} /></span>
          <span className="vbar-wave" aria-hidden>
            {Array.from({ length: BARS }, (_, i) => <i key={i} ref={(el) => { barEls.current[i] = el; }} />)}
          </span>
          <span className="vbar-text">{holding ? `${seconds.toFixed(1)}s · ${t("release")}` : label ?? t("correct")}</span>
        </button>
      </div>
    );
  }

  return (
    <div ref={root} className={`orb-wrap ${holding ? "is-live" : ""} ${working ? "is-working" : ""}`}>
      <div className="orb-stage">
        <span className="orb-ring r1" /><span className="orb-ring r2" /><span className="orb-ring r3" />
        <button type="button" className="orb" disabled={disabled || working} aria-label={label ?? t("hold")} {...handlers}>
          <span className="orb-core">
            {working ? <span className="orb-spin" /> : <Icon name="mic" size={46} />}
          </span>
        </button>
      </div>
      <div className="orb-label" aria-live="polite">
        {holding ? <><b>{seconds.toFixed(1)}s</b> · {t("release")}</> : working ? null : label ?? t("hold")}
      </div>
      <div className="orb-wave" aria-hidden>
        {Array.from({ length: BARS }, (_, i) => <i key={i} ref={(el) => { barEls.current[i] = el; }} />)}
      </div>
    </div>
  );
}
