import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { queryKeys, useReviews } from "../api/queries";
import { type ReviewDecision } from "../components/DecisionBar";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { type HistoryEntry, ReviewHistory } from "../components/ReviewHistory";
import { ReviewWorkspace } from "../components/ReviewWorkspace";

const decisionLabels: Record<ReviewDecision, string> = {
  ACCEPT: "acceptance",
  REJECT: "rejection",
  UNCERTAIN: "uncertain",
};

export function ReviewQueue() {
  const reviews = useReviews();
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState<ReviewDecision | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const trigger = useRef<HTMLElement | null>(null);
  const cancelButton = useRef<HTMLButtonElement | null>(null);
  const confirmButton = useRef<HTMLButtonElement | null>(null);
  const image = reviews.data?.items[0];

  function choose(value: ReviewDecision) {
    trigger.current = document.activeElement as HTMLElement;
    setDecision(value);
    setMessage(null);
  }

  const close = useCallback(() => {
    setDecision(null);
    queueMicrotask(() => trigger.current?.focus());
  }, []);

  useEffect(() => {
    if (!decision) return;
    const background = document.querySelector<HTMLElement>(".app-shell");
    background?.setAttribute("inert", "");
    cancelButton.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab") return;
      const cancel = cancelButton.current;
      const confirm = confirmButton.current;
      if (!cancel || !confirm) return;
      if (event.shiftKey && document.activeElement === cancel) {
        event.preventDefault();
        confirm.focus();
      } else if (!event.shiftKey && document.activeElement === confirm) {
        event.preventDefault();
        cancel.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      background?.removeAttribute("inert");
    };
  }, [close, decision]);

  async function confirm() {
    if (!decision || !image || saving) return;
    setSaving(true);
    try {
      const result = await api.recordReview(image.id, {
        decision,
        note: note || null,
        expected_revision: image.revision,
      });
      setHistory((entries) => [
        ...entries,
        {
          revision: result.revision,
          decision: result.decision,
          createdAt: result.created_at,
        },
      ]);
      setMessage(`Human decision saved for ${image.filename}.`);
      setNote("");
      close();
      await queryClient.invalidateQueries({ queryKey: queryKeys.reviews });
    } catch (error) {
      close();
      setMessage(
        error instanceof ApiError && error.status === 409
          ? "This item was reviewed elsewhere"
          : "Decision was not saved. Check the connection and try again.",
      );
      if (error instanceof ApiError && error.status === 409) await reviews.refetch();
    } finally {
      setSaving(false);
    }
  }

  const dialog = decision && image
    ? createPortal(
        <div className="dialog-backdrop" role="presentation">
          <section
            className="confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-confirm-title"
            aria-label={`Confirm human ${decisionLabels[decision]}`}
          >
            <span className="eyebrow">Human decision confirmation</span>
            <h2 id="review-confirm-title">Confirm human {decisionLabels[decision]}</h2>
            <p>
              You are about to record <strong>{decision}</strong> for <strong>{image.filename}</strong>.
              This creates a new audit revision.
            </p>
            <div>
              <button ref={cancelButton} type="button" className="button button--secondary" onClick={close}>
                Cancel
              </button>
              <button ref={confirmButton} type="button" className="button" disabled={saving} onClick={confirm}>
                {saving ? "Saving…" : `Confirm ${decision.toLowerCase()}`}
              </button>
            </div>
          </section>
        </div>,
        document.body,
      )
    : null;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Human decision workspace</span>
          <h1>Review queue</h1>
          <p className="lede">
            Resolve model REVIEW evidence deliberately. These actions are human audit decisions,
            not model predictions.
          </p>
        </div>
        <div className="queue-count">
          <strong className="numeric">{reviews.data?.total ?? "—"}</strong>
          <span>unresolved</span>
        </div>
      </header>
      {message && <p className="review-message" role="status">{message}</p>}
      {reviews.isError ? (
        <ErrorPanel message="The review queue could not be loaded." onRetry={() => reviews.refetch()} />
      ) : reviews.isLoading ? (
        <p role="status">Loading review queue…</p>
      ) : image ? (
        <>
          <ReviewWorkspace image={image} note={note} onNote={setNote} onChoose={choose} disabled={saving} />
          <ReviewHistory entries={history} />
        </>
      ) : (
        <EmptyState title="Review queue is clear">
          No unresolved model REVIEW items require a human decision.
        </EmptyState>
      )}
      {dialog}
    </div>
  );
}
