import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

export function Bootstrap() {
  return <main><h1>MVTec AD 2 Inspection Workstation</h1></main>;
}

const root = document.getElementById("root");
if (!root) throw new Error("Application root is missing");
createRoot(root).render(<StrictMode><Bootstrap /></StrictMode>);
