import { useEffect, useState } from "react";
import { setUnauthorizedHandler, session } from "./api";
import { I18nProvider } from "./i18n";
import { Login } from "./Login";
import { ManagerApp } from "./manager/ManagerApp";
import { RepApp } from "./rep/RepApp";
import type { User } from "./types";
import { Intro } from "./intro/Intro";
import { ApkLink } from "./ApkLink";

function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true), down = () => setOnline(false);
    window.addEventListener("online", up); window.addEventListener("offline", down);
    return () => { window.removeEventListener("online", up); window.removeEventListener("offline", down); };
  }, []);
  return online;
}

function Root() {
  const [user, setUser] = useState<User | null>(() => (session.token ? session.user : null));
  const online = useOnline();

  useEffect(() => { setUnauthorizedHandler(() => { session.clear(); setUser(null); }); }, []);

  const signOut = () => setUser(null);
  return (
    <>
      {!user ? <Login onLogin={setUser} />
        : user.role === "rep" ? <RepApp user={user} online={online} onSignOut={signOut} />
        : <ManagerApp user={user} online={online} onSignOut={signOut} />}
      <ApkLink loggedIn={!!user} />
    </>
  );
}

export default function App() {
  const [intro, setIntro] = useState(true);
  useEffect(() => { document.getElementById("boot")?.remove(); }, []);
  return (
    <I18nProvider>
      <Root />
      {intro && <Intro onDone={() => setIntro(false)} />}
    </I18nProvider>
  );
}
