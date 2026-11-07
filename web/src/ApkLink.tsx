import { Capacitor } from "@capacitor/core";
import { useEffect } from "react";
import { Icon } from "./Icon";

/** Website-only shortcut to install the Android app; hidden inside the app itself. */
export function ApkLink() {
  const native = Capacitor.isNativePlatform();
  useEffect(() => {
    if (native) return;
    document.documentElement.classList.add("has-apk");
    return () => document.documentElement.classList.remove("has-apk");
  }, [native]);
  if (native) return null;
  return (
    <a className="apk-link" href="/BolBazaar.apk" download="BolBazaar.apk" title="Install the Android app" aria-label="Install the Android app">
      <Icon name="download" size={18} />
      <span>Get the Android app</span>
    </a>
  );
}
