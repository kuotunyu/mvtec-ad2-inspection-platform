import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const navigation = [
  ["/", "Overview", "01"],
  ["/inspect", "New inspection", "02"],
  ["/review", "Review queue", "03"],
  ["/evidence", "Model & evidence", "04"],
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return <div className="app-shell">
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark" aria-hidden="true">M2</span><div><strong>Inspection OS</strong><small>MVTec AD 2</small></div></div>
      <nav aria-label="Workstation">
        {navigation.map(([to, label, index]) => <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => isActive ? "active" : undefined}><span>{index}</span>{label}</NavLink>)}
      </nav>
      <div className="system-state" aria-label="System state"><span className="pulse" aria-hidden="true"/><div><strong>Backend ready</strong><small>Worker heartbeat: current</small></div></div>
    </aside>
    <div className="main-column">
      <header className="topbar"><div><span className="eyebrow">Industrial evidence workstation</span><strong>Shift A · Local runtime</strong></div><div className="operator"><span aria-hidden="true">KY</span><div><strong>Review operator</strong><small>Human decisions enabled</small></div></div></header>
      <main id="workspace" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}
