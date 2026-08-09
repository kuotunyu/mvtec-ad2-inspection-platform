import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { EmptyState } from "../components/EmptyState";
import { Dashboard } from "../pages/Dashboard";
import { JobDetail } from "../pages/JobDetail";
import { NewInspection } from "../pages/NewInspection";

function Placeholder({ title, kicker }: { title: string; kicker: string }) {
  return <div className="page"><header className="page-header"><div><span className="eyebrow">{kicker}</span><h1>{title}</h1></div></header><EmptyState title="Surface ready">Product workflow is being connected to the verified API contract.</EmptyState></div>;
}

export function App() {
  return <AppShell><Routes>
    <Route path="/" element={<Dashboard />} />
    <Route path="/inspect" element={<NewInspection />} />
    <Route path="/jobs/:jobId" element={<JobDetail />} />
    <Route path="/review" element={<Placeholder title="Review queue" kicker="Human decision workspace" />} />
    <Route path="/evidence" element={<Placeholder title="Model & evidence" kicker="Provenance and limitations" />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></AppShell>;
}
