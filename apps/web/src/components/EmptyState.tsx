import type { ReactNode } from "react";

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <section className="empty-state"><span aria-hidden="true">◇</span><h2>{title}</h2><p>{children}</p></section>;
}
