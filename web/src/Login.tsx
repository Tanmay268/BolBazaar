import { useState } from "react";
import { ApiFailure, api, session } from "./api";
import { Icon, Logo } from "./Icon";
import { LangToggle, useI18n } from "./i18n";
import type { User } from "./types";

const DEMO = [
  { user: "asha", label: "Asha", sub: "Field rep", icon: "mic" },
  { user: "meera", label: "Meera", sub: "Manager", icon: "trend" },
];

export function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(u = username, p = password) {
    setBusy(true); setError(null);
    try {
      const { token, user } = await api.login(u.trim(), p);
      session.save(token, user);
      onLogin(user);
    } catch (e) {
      setError(e instanceof ApiFailure ? (e.isNetwork ? "Can't reach the server. Is the API running?" : e.message) : "Sign-in failed.");
    } finally { setBusy(false); }
  }

  return (
    <div className="landing">
      <div className="landing-top"><span className="brand"><Logo size={30} /><span>FieldForce<b>AI</b></span></span><LangToggle /></div>

      <section className="landing-hero">
        <div className="eq" aria-hidden>{Array.from({ length: 9 }, (_, i) => <i key={i} style={{ animationDelay: `${i * 90}ms` }} />)}</div>
        <h1>{t("tagline")}</h1>
        <p>{t("landingSub")}</p>
        <ol className="how">
          {(["step1", "step2", "step3"] as const).map((k, i) => <li key={k}><span>{i + 1}</span>{t(k)}</li>)}
        </ol>
      </section>

      <section className="signin card">
        <h2>{t("signIn")}</h2>
        <div className="chips chips-2">
          {DEMO.map((d) => (
            <button key={d.user} className="demo-card" disabled={busy} onClick={() => void submit(d.user, "demo123")}>
              <span className="lcard-ico"><Icon name={d.icon} size={18} /></span>
              <b>{d.label}</b><small>{d.sub}</small>
            </button>
          ))}
        </div>
        <div className="or"><span>or</span></div>
        <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="login-form">
          <label>{t("username")}<input autoCapitalize="none" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
          <label>{t("password")}<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          <button className="btn btn-primary btn-wide" disabled={busy || !username || !password}>{busy ? <span className="spinner spinner-on" /> : t("signIn")}</button>
        </form>
        {error && <div className="error" role="alert">{error}</div>}
        <small className="demo-note">Demo accounts use password demo123.</small>
      </section>
    </div>
  );
}
