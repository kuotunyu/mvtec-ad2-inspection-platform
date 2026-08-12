export function ErrorPanel({ title = "無法載入", message, onRetry }: { title?: string; message: string; onRetry?: () => void }) {
  return <section className="error-panel" role="alert"><strong>{title}</strong><p>{message}</p>{onRetry && <button onClick={onRetry}>再試一次</button>}</section>;
}
