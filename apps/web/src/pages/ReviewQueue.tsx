import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { queryKeys, useReviews } from "../api/queries";
import { type ReviewDecision } from "../components/DecisionBar";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { type HistoryEntry, ReviewHistory } from "../components/ReviewHistory";
import { ReviewWorkspace } from "../components/ReviewWorkspace";

const decisionLabels: Record<ReviewDecision, string> = { ACCEPT: "acceptance", REJECT: "rejection", UNCERTAIN: "uncertain" };

export function ReviewQueue() {
  const reviews = useReviews();
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState<ReviewDecision | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const trigger = useRef<HTMLElement | null>(null);
  const image = reviews.data?.items[0];
  function choose(value: ReviewDecision) { trigger.current = document.activeElement as HTMLElement; setDecision(value); setMessage(null); }
  function close() { setDecision(null); queueMicrotask(() => trigger.current?.focus()); }
  async function confirm() {
    if (!decision || !image || saving) return;
    setSaving(true);
    try {
      const result = await api.recordReview(image.id, { decision, note: note || null, expected_revision: image.revision });
      setHistory((entries) => [...entries, { revision: result.revision, decision: result.decision, createdAt: result.created_at }]);
      setMessage(`Human decision saved for ${image.filename}.`); setNote(""); close();
      await queryClient.invalidateQueries({ queryKey: queryKeys.reviews });
    } catch (error) {
      close();
      setMessage(error instanceof ApiError && error.status === 409 ? "This item was reviewed elsewhere" : "Decision was not saved. Check the connection and try again.");
      if (error instanceof ApiError && error.status === 409) await reviews.refetch();
    } finally { setSaving(false); }
  }
  return <div className="page"><header className="page-header"><div><span className="eyebrow">Human decision workspace</span><h1>Review queue</h1><p className="lede">Resolve model REVIEW evidence deliberately. These actions are human audit decisions, not model predictions.</p></div><div className="queue-count"><strong className="numeric">{reviews.data?.total ?? "—"}</strong><span>unresolved</span></div></header>{message && <p className="review-message" role="status">{message}</p>}{reviews.isError ? <ErrorPanel message="The review queue could not be loaded." onRetry={() => reviews.refetch()} /> : reviews.isLoading ? <p role="status">Loading review queue…</p> : image ? <><ReviewWorkspace image={image} note={note} onNote={setNote} onChoose={choose} disabled={saving} /><ReviewHistory entries={history} /></> : <EmptyState title="Review queue is clear">No unresolved model REVIEW items require a human decision.</EmptyState>}{decision && image && <div className="dialog-backdrop" role="presentation"><section className="confirm-dialog" role="dialog" aria-modal="true" aria-label={`Confirm human ${decisionLabels[decision]}`}><span className="eyebrow">Human decision confirmation</span><h2>Confirm {decision.toLowerCase()}</h2><p>You are about to record <strong>{decision}</strong> for <strong>{image.filename}</strong>. This creates a new audit revision.</p><div><button type="button" className="button button--secondary" onClick={close}>Cancel</button><button type="button" className="button" disabled={saving} onClick={confirm}>{saving ? "Saving…" : `Confirm ${decision.toLowerCase()}`}</button></div></section></div>}</div>;
}
