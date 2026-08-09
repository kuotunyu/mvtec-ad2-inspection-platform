import { useRef, useState } from "react";

export function UploadDropzone({ files, onChange }: { files: File[]; onChange: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  return <div className={`dropzone ${dragging ? "dropzone--active" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); onChange([...files, ...event.dataTransfer.files]); }}>
    <span aria-hidden="true" className="drop-icon">＋</span><strong>Drop inspection images here</strong><p>PNG, JPEG, or WebP · up to 25 MB each</p>
    <button type="button" className="button button--secondary" onClick={() => input.current?.click()}>Choose files</button>
    <input ref={input} className="visually-hidden" aria-label="Inspection files" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={(event) => onChange([...files, ...Array.from(event.target.files ?? [])])} />
  </div>;
}
