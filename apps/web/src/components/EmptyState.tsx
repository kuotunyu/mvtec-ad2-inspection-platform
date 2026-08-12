import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <section className="empty-state"><span className="empty-state-mark" aria-hidden="true" /><h2>{title}</h2><p>{children}</p></section>;
}
