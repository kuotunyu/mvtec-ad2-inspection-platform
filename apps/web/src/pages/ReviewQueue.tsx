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
  ACCEPT: "接受",
  REJECT: "拒絕",
  UNCERTAIN: "不確定",
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
      setMessage(`已儲存 ${image.filename} 的人工處置。`);
      setNote("");
      close();
      await queryClient.invalidateQueries({ queryKey: queryKeys.reviews });
    } catch (error) {
      close();
      setMessage(
        error instanceof ApiError && error.status === 409
          ? "此項目已由其他操作員完成覆核"
          : "無法儲存處置。請檢查連線後再試一次。",
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
            aria-label={`確認人工${decisionLabels[decision]}`}
          >
            <h2 id="review-confirm-title">確認人工{decisionLabels[decision]}</h2>
            <p>
              即將為 <strong>{image.filename}</strong> 記錄 <strong>{decision}</strong>，並建立新的 audit revision。
            </p>
            <div>
              <button ref={cancelButton} type="button" className="button button--secondary" onClick={close}>
                取消
              </button>
              <button ref={confirmButton} type="button" className="button" disabled={saving} onClick={confirm}>
                {saving ? "儲存中…" : `確認${decisionLabels[decision]}`}
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
          <h1>待覆核項目</h1>
          <p className="lede">
            逐項處理 Model REVIEW 證據。這些是人工 audit decision，不是 model prediction。
          </p>
        </div>
        <div className="queue-count">
          <strong className="numeric">{reviews.data?.total ?? "—"}</strong>
          <span>未處置</span>
        </div>
      </header>
      {message && <p className="review-message" role="status">{message}</p>}
      {reviews.isError ? (
        <ErrorPanel message="無法載入待覆核項目。" onRetry={() => reviews.refetch()} />
      ) : reviews.isLoading ? (
        <p role="status">正在載入待覆核項目…</p>
      ) : image ? (
        <>
          <ReviewWorkspace image={image} note={note} onNote={setNote} onChoose={choose} disabled={saving} />
          <ReviewHistory entries={history} />
        </>
      ) : (
        <EmptyState title="待覆核項目已清空">
          目前沒有需要人工處置的 Model REVIEW 證據。
        </EmptyState>
      )}
      {dialog}
    </div>
  );
}
