import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useSystemStatus } from "../api/queries";

const navigation = [
  ["/", "作業總覽", "01"],
  ["/inspect", "建立檢測", "02"],
  ["/review", "待覆核項目", "03"],
  ["/evidence", "Model 與證據", "04"],
] as const;

const workerLabels = { current: "正常", stale: "過期", missing: "無資料", unknown: "未知" } as const;

export function AppShell({ children }: { children: ReactNode }) {
  const system = useSystemStatus();
  const backend = system.isError ? "Backend 無法連線" : system.data ? "Backend 已就緒" : "正在檢查 Backend";
  const worker = system.data?.worker_status ?? "unknown";
  const workerDisplay = workerLabels[worker as keyof typeof workerLabels] ?? worker;
  const indicator = system.isError
    ? "error"
    : !system.data
      ? "unknown"
      : worker === "current"
        ? "current"
        : worker === "stale"
          ? "warning"
          : "unknown";
  return <div className="app-shell">
    <a className="skip-link" href="#workspace">跳至主要工作區</a>
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark" aria-hidden="true">M2</span><div><strong>工業檢測平台</strong><small translate="no">MVTec AD 2</small></div></div>
      <nav aria-label="檢測工作站">
        {navigation.map(([to, label, index]) => <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => isActive ? "active" : undefined}><span aria-hidden="true">{index}</span>{label}</NavLink>)}
      </nav>
      <div className="system-state" aria-label="系統狀態"><span className={`pulse pulse--${indicator}`} aria-hidden="true"/><div><strong>{backend}</strong><small>Worker heartbeat：{workerDisplay}</small></div></div>
    </aside>
    <div className="main-column">
      <header className="topbar"><div className="topbar-context"><strong>Industrial Evidence Workstation</strong><span>產線 A · 本機執行環境</span></div><div className="operator"><span aria-hidden="true">KY</span><div><strong>覆核操作員</strong><small>人工決策已啟用</small></div></div></header>
      <main id="workspace" tabIndex={-1}>{children}</main>
    </div>
  </div>;
}
