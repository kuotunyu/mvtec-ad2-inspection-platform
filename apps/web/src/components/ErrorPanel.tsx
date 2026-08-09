export function ErrorPanel({ title = "Unable to load", message, onRetry }: { title?: string; message: string; onRetry?: () => void }) {
  return <section className="error-panel" role="alert"><strong>{title}</strong><p>{message}</p>{onRetry && <button onClick={onRetry}>Try again</button>}</section>;
}
