import { Wordmark } from "./brand";
import { Icon } from "./Icon";
import { useI18n } from "./i18n";

export function AppBar({ onMenu, online }: { onMenu: () => void; online: boolean }) {
  const { t } = useI18n();
  return (
    <header className="appbar">
      <button className="appbar-btn" onClick={onMenu} aria-label="Menu"><Icon name="menu" size={26} /></button>
      <Wordmark />
      {!online && <span className="chip-red appbar-off"><Icon name="wifioff" size={12} />{t("offline")}</span>}
    </header>
  );
}

export interface NavItem { id: string; label: string; icon: string; badge?: number }

export function BottomNav({ items, active, onSelect, center }: {
  items: NavItem[]; active: string; onSelect: (id: string) => void; center?: { label: string; onClick: () => void };
}) {
  const half = Math.ceil(items.length / 2);
  const tab = (item: NavItem) => (
    <button key={item.id} className={`bnav-item ${active === item.id ? "on" : ""}`} onClick={() => onSelect(item.id)} aria-current={active === item.id ? "page" : undefined}>
      <span className="bnav-ico"><Icon name={item.icon} size={22} />{!!item.badge && <i className="badge">{item.badge}</i>}</span>
      <span>{item.label}</span>
    </button>
  );
  return (
    <nav className={`bnav ${center ? "bnav-mic" : ""}`} aria-label="Sections">
      {items.slice(0, half).map(tab)}
      {center && (
        <div className="bnav-mic-slot">
          <button className="mic-fab" onClick={center.onClick} aria-label={center.label}>
            <span className="mic-ring" aria-hidden /><span className="mic-ring mic-ring-2" aria-hidden />
            <span className="mic-core"><Icon name="mic" size={26} /></span>
          </button>
        </div>
      )}
      {items.slice(half).map(tab)}
    </nav>
  );
}

export function Sidebar({ items, active, onSelect, open, onClose, footer }: {
  items: NavItem[]; active: string; onSelect: (id: string) => void; open: boolean; onClose: () => void; footer: React.ReactNode;
}) {
  return (
    <>
      {open && <div className="side-scrim" onClick={onClose} aria-hidden />}
      <aside className={`side ${open ? "side-open" : ""}`} aria-label="Navigation">
        <div className="side-top"><Wordmark light /><button className="side-close" onClick={onClose} aria-label="Close menu"><Icon name="x" size={22} /></button></div>
        <nav>
          {items.map((item) => (
            <button key={item.id} className={`side-item ${active === item.id ? "on" : ""}`} onClick={() => { onSelect(item.id); onClose(); }} aria-current={active === item.id ? "page" : undefined}>
              <Icon name={item.icon} size={20} />{item.label}
              {!!item.badge && <i className="badge badge-inline">{item.badge}</i>}
            </button>
          ))}
        </nav>
        <div className="side-foot">{footer}</div>
      </aside>
    </>
  );
}
