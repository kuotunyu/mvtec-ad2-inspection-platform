export function UploadManifest({ files, onRemove }: { files: File[]; onRemove: (index: number) => void }) {
  if (!files.length) return null;
  const total = files.reduce((sum, file) => sum + file.size, 0);
  return <section className="manifest" aria-label="Upload manifest"><header><strong>{files.length} files selected</strong><span className="numeric">{(total / 1024).toFixed(1)} KiB total</span></header><ul>{files.map((file, index) => <li key={`${file.name}-${index}`}><span aria-hidden="true">▧</span><div><strong>{file.name}</strong><small>{file.type || "unknown type"} · {(file.size / 1024).toFixed(1)} KiB</small></div><span className="validation">Ready</span><button type="button" aria-label={`Remove ${file.name}`} onClick={() => onRemove(index)}>Remove</button></li>)}</ul></section>;
}
