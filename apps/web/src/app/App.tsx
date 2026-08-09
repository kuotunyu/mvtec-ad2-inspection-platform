import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { Dashboard } from "../pages/Dashboard";
import { JobDetail } from "../pages/JobDetail";
import { ModelEvidence } from "../pages/ModelEvidence";
import { NewInspection } from "../pages/NewInspection";
import { ReviewQueue } from "../pages/ReviewQueue";

export function App() {
  return <AppShell><Routes>
    <Route path="/" element={<Dashboard />} />
    <Route path="/inspect" element={<NewInspection />} />
    <Route path="/jobs/:jobId" element={<JobDetail />} />
    <Route path="/review" element={<ReviewQueue />} />
    <Route path="/evidence" element={<ModelEvidence />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></AppShell>;
}
