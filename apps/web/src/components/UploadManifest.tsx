export function UploadManifest({ files, onRemove }: { files: File[]; onRemove: (index: number) => void }) {
  if (!files.length) return null;
  const total = files.reduce((sum, file) => sum + file.size, 0);
  return <section className="manifest" aria-label="上傳檔案清單"><header><strong>{files.length} 個檔案已選取</strong><span className="numeric">共 {(total / 1024).toFixed(1)} KiB</span></header><ul>{files.map((file, index) => <li key={`${file.name}-${index}`}><span className="file-marker" aria-hidden="true" /><div><strong>{file.name}</strong><small>{file.type || "未知類型"} · {(file.size / 1024).toFixed(1)} KiB</small></div><span className="validation">可使用</span><button type="button" aria-label={`移除 ${file.name}`} onClick={() => onRemove(index)}>移除</button></li>)}</ul></section>;
}
