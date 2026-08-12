import { useRef, useState } from "react";

export function UploadDropzone({ files, onChange }: { files: File[]; onChange: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  return <div className={`dropzone ${dragging ? "dropzone--active" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); onChange([...files, ...event.dataTransfer.files]); }}>
    <span aria-hidden="true" className="drop-icon"><span /></span><strong>將檢測影像拖曳至此</strong><p>PNG、JPEG 或 WebP · 單檔上限 25 MB</p>
    <button type="button" className="button button--secondary" onClick={() => input.current?.click()}>選擇檔案</button>
    <input ref={input} className="visually-hidden" aria-label="檢測影像檔案" name="inspection-files" type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={(event) => onChange([...files, ...Array.from(event.target.files ?? [])])} />
  </div>;
}
