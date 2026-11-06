import { Icon, Logo } from "./Icon";
import { LangToggle, useI18n } from "./i18n";
import type { User } from "./types";

export function Header({ user, online }: { user: User; online: boolean }) {
  const { t } = useI18n();
  return (
    <header className="top">
      <div className="brand"><Logo size={30} /><span>FieldForce<b>AI</b></span></div>
      <div className="top-right">
        {!online && <span className="tag tag-warn"><Icon name="wifioff" size={12} />{t("offline")}</span>}
        <LangToggle />
        <span className="avatar" title={`${user.name} · ${user.role}`}>{user.name.slice(0, 1)}</span>
      </div>
    </header>
  );
}

export interface NavItem { id: string; label: string; icon: string; badge?: number }

export function BottomNav({ items, active, onSelect, center }: { items: NavItem[]; active: string; onSelect: (id: string) => void; center?: NavItem }) {
  const render = (item: NavItem) => (
    <button key={item.id} className={`nav-item ${active === item.id ? "on" : ""}`} onClick={() => onSelect(item.id)} aria-current={active === item.id ? "page" : undefined}>
      <span className="nav-ico"><Icon name={item.icon} size={22} />{!!item.badge && <i className="badge">{item.badge}</i>}</span>
      <span>{item.label}</span>
    </button>
  );
  const half = center ? Math.ceil(items.length / 2) : items.length;
  return (
    <nav className="nav" aria-label="Sections">
      {items.slice(0, half).map(render)}
      {center && (
        <button className={`nav-fab ${active === center.id ? "on" : ""}`} onClick={() => onSelect(center.id)} aria-label={center.label}>
          <Icon name={center.icon} size={28} />
        </button>
      )}
      {items.slice(half).map(render)}
    </nav>
  );
}
