import { useState } from "react";
import { ApiFailure, api, session } from "./api";
import { Lockup, Storefront } from "./brand";
import { Icon } from "./Icon";
import { LangToggle, useI18n } from "./i18n";
import type { User } from "./types";

const DEMO = [
  { user: "asha", label: "Asha", sub: "Field executive", icon: "mic" },
  { user: "meera", label: "Meera", sub: "Area manager", icon: "chart" },
];

export function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [signup, setSignup] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState<"rep" | "manager">("rep");
  const [territoryId, setTerritoryId] = useState("");
  const [signupCode, setSignupCode] = useState("");
  const [options, setOptions] = useState<{ territories: { id: string; name: string }[]; managerSignup: boolean; signupOpen: boolean } | null>(null);

  const fail = (e: unknown, fallback: string) =>
    setError(e instanceof ApiFailure ? (e.isNetwork ? "Can't reach the server. Is the API running?" : e.message) : fallback);

  async function submit(u = username, p = password) {
    setBusy(true); setError(null);
    try {
      const { token, user } = await api.login(u.trim(), p);
      session.save(token, user);
      onLogin(user);
    } catch (e) {
      fail(e, "Sign-in failed.");
    } finally { setBusy(false); }
  }

  async function register() {
    setBusy(true); setError(null);
    try {
      const { token, user } = await api.register({
        username: username.trim().toLowerCase(), name: name.trim(), password, role,
        territoryId: role === "rep" && territoryId ? territoryId : undefined,
        signupCode: role === "manager" ? signupCode : undefined,
      });
      session.save(token, user);
      onLogin(user);
    } catch (e) {
      fail(e, "Could not create the account.");
    } finally { setBusy(false); }
  }

  async function toggleMode() {
    setError(null);
    const next = !signup;
    setSignup(next);
    if (next && !options) {
      try {
        const o = await api.signupOptions();
        setOptions(o);
        setTerritoryId(o.territories[0]?.id ?? "");
        if (!o.signupOpen) setError("Sign-up is closed. Ask your administrator for an account.");
      } catch (e) { fail(e, "Could not load sign-up options."); }
    }
  }

  return (
    <div className="landing">
      <div className="landing-top"><span className="rule" /><LangToggle /></div>
      <section className="landing-hero">
        <Lockup />
        <p className="landing-tag">{t("tagline")}</p>
        <Storefront className="landing-art" />
        <ol className="how">
          {(["step1", "step2", "step3"] as const).map((k, i) => <li key={k}><span>{i + 1}</span>{t(k)}</li>)}
        </ol>
      </section>

      <section className="signin">
        <h2>{signup ? t("createAccount") : t("signIn")}</h2>
        {!signup && (
          <>
            <div className="demo-grid">
              {DEMO.map((d) => (
                <button key={d.user} className="demo-card" disabled={busy} onClick={() => void submit(d.user, "demo123")}>
                  <Icon name={d.icon} size={22} /><b>{d.label}</b><small>{d.sub}</small>
                </button>
              ))}
            </div>
            <div className="or"><span>or</span></div>
          </>
        )}
        {signup ? (
          <form onSubmit={(e) => { e.preventDefault(); void register(); }} className="login-form">
            <label>{t("fullName")}<input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label>{t("username")}<input autoCapitalize="none" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
            <label>{t("password")}<input type="password" autoComplete="new-password" minLength={8} placeholder={t("passwordHint")} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            <label>{t("iAmA")}
              <select value={role} onChange={(e) => setRole(e.target.value as "rep" | "manager")}>
                <option value="rep">{t("roleRep")}</option>
                {options?.managerSignup && <option value="manager">{t("roleManager")}</option>}
              </select>
            </label>
            {role === "rep" && !!options?.territories.length && (
              <label>{t("territory")}
                <select value={territoryId} onChange={(e) => setTerritoryId(e.target.value)}>
                  {options.territories.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                </select>
              </label>
            )}
            {role === "manager" && <label>{t("managerCode")}<input type="password" autoComplete="off" value={signupCode} onChange={(e) => setSignupCode(e.target.value)} /></label>}
            <button className="btn btn-red btn-wide btn-lg" disabled={busy || options?.signupOpen === false || !name.trim() || !username || password.length < 8 || (role === "manager" && !signupCode)}>
              {busy ? <span className="spinner spinner-on" /> : <>{t("createAccount")}<Icon name="arrow" size={20} /></>}
            </button>
          </form>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="login-form">
            <label>{t("username")}<input autoCapitalize="none" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
            <label>{t("password")}<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            <button className="btn btn-red btn-wide btn-lg" disabled={busy || !username || !password}>{busy ? <span className="spinner spinner-on" /> : <>{t("signIn")}<Icon name="arrow" size={20} /></>}</button>
          </form>
        )}
        {error && <div className="error" role="alert">{error}</div>}
        <button type="button" className="link-btn" onClick={() => void toggleMode()}>{signup ? t("haveAccount") : t("newHere")}</button>
        {!signup && <small className="demo-note">Demo accounts use password demo123.</small>}
      </section>
    </div>
  );
}
