/**
 * Microphone capture that produces a 16 kHz mono 16-bit PCM WAV on every platform
 * (desktop browsers, Android WebView through Capacitor). WAV is on Gnani's accepted list,
 * so no server-side transcoding is needed and web and Android behave identically.
 */

export const TARGET_RATE = 16000;
export const MAX_SECONDS = 110;
export const MIN_SECONDS = 0.6;

export class RecorderError extends Error {
  constructor(public kind: "denied" | "unsupported" | "short" | "failed", message: string) { super(message); }
}

export function downsample(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return input;
  const ratio = from / to;
  const length = Math.floor(input.length / ratio);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = end > start ? sum / (end - start) : input[start] ?? 0;
  }
  return out;
}

export function encodeWav(samples: Float32Array, rate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset: number, text: string) => { for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i)); };
  write(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);          // PCM
  view.setUint16(22, 1, true);          // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);   // byte rate
  view.setUint16(32, 2, true);          // block align
  view.setUint16(34, 16, true);         // bits per sample
  write(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export class WavRecorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private analyser: AnalyserNode | null = null;
  private chunks: Float32Array[] = [];
  private frames = 0;
  private raf = 0;
  private startedAt = 0;
  private active = false;

  get seconds() { return this.ctx ? this.frames / this.ctx.sampleRate : 0; }
  get recording() { return this.active; }

  /** `onLevel` receives 0..1 roughly every animation frame; `onLimit` fires when MAX_SECONDS is reached. */
  async start(onLevel: (level: number) => void, onLimit: () => void): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) throw new RecorderError("unsupported", "This browser can't record audio.");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      throw new RecorderError("denied", "Microphone permission was denied.");
    }
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.ctx = new Ctx();
    if (this.ctx.state === "suspended") await this.ctx.resume();
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 512;
    this.processor = this.ctx.createScriptProcessor(4096, 1, 1);
    this.chunks = [];
    this.frames = 0;
    this.active = true;
    this.startedAt = performance.now();
    this.processor.onaudioprocess = (event) => {
      if (!this.active) return;
      const data = event.inputBuffer.getChannelData(0);
      this.chunks.push(new Float32Array(data));
      this.frames += data.length;
      if (this.seconds >= MAX_SECONDS) onLimit();
    };
    this.source.connect(this.analyser);
    this.source.connect(this.processor);
    this.processor.connect(this.ctx.destination); // required for the processor to run; output is silent
    const buf = new Uint8Array(this.analyser.fftSize);
    const tick = () => {
      if (!this.active || !this.analyser) return;
      this.analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (let i = 0; i < buf.length; i++) peak = Math.max(peak, Math.abs(buf[i] - 128) / 128);
      onLevel(Math.min(1, peak * 1.8));
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  async stop(): Promise<Blob> {
    const rate = this.ctx?.sampleRate ?? TARGET_RATE;
    const heldMs = performance.now() - this.startedAt;
    this.active = false;
    cancelAnimationFrame(this.raf);
    this.processor?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.ctx?.close().catch(() => undefined);
    const total = this.chunks.reduce((n, c) => n + c.length, 0);
    const merged = new Float32Array(total);
    let offset = 0;
    for (const chunk of this.chunks) { merged.set(chunk, offset); offset += chunk.length; }
    this.chunks = [];
    this.ctx = this.stream = this.source = this.processor = this.analyser = null;
    if (heldMs / 1000 < MIN_SECONDS || total / rate < MIN_SECONDS) throw new RecorderError("short", "Hold the button a little longer.");
    return encodeWav(downsample(merged, rate, TARGET_RATE), TARGET_RATE);
  }

  cancel() {
    this.active = false;
    cancelAnimationFrame(this.raf);
    this.processor?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close().catch(() => undefined);
    this.chunks = [];
    this.ctx = this.stream = this.source = this.processor = this.analyser = null;
  }
}
