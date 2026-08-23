import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateJob, useSystemStatus } from "../api/queries";
import { UploadDropzone } from "../components/UploadDropzone";
import { UploadManifest } from "../components/UploadManifest";

const categories = ["can", "fabric", "fruit_jelly", "rice", "sheet_metal", "vial", "wallplugs", "walnuts"];

function formatCapacity(bytes: number) {
  const mebibyte = 1024 * 1024;
  const kibibyte = 1024;
  if (bytes % mebibyte === 0) return `${bytes / mebibyte} MiB`;
  if (bytes % kibibyte === 0) return `${bytes / kibibyte} KiB`;
  return `${bytes.toLocaleString("en-US")} B`;
}

export function NewInspection() {
  const [category, setCategory] = useState("can");
  const [files, setFiles] = useState<File[]>([]);
  const create = useCreateJob();
  const system = useSystemStatus();
  const navigate = useNavigate();
  const limits = system.data?.ingestion_limits;
  const maxUploadLabel = limits ? formatCapacity(limits.max_upload_bytes) : "等待 Backend 設定";
  const valid = Boolean(
    limits
    && files.length > 0
    && files.length <= limits.max_archive_files
    && files.every((file) => file.size <= limits.max_upload_bytes),
  );
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid || create.isPending) return;
    const result = await create.mutateAsync({ category, files });
    navigate(`/jobs/${result.id}`, { state: { queuedCount: result.image_count } });
  }
  return <div className="page page--narrow"><header className="page-header"><div><h1>建立檢測</h1><p className="lede">上傳產品影像進行 anomaly scoring。Model outcome 僅作為覆核證據，不會自動做最終拒絕。</p></div></header>
    <form className="intake" onSubmit={submit}><section className="panel intake-panel"><div className="field"><label htmlFor="component-category">Component category</label><select id="component-category" name="category" autoComplete="off" value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select><small>此 category 會自動綁定目前 frozen Champion。</small></div><UploadDropzone files={files} maxUploadLabel={maxUploadLabel} onChange={setFiles} /><UploadManifest files={files} onRemove={(index) => setFiles(files.filter((_, candidate) => candidate !== index))} />{limits && !valid && files.length > 0 && <p className="field-error" role="alert">每個檔案不得超過 {maxUploadLabel}，單批最多 {limits.max_archive_files.toLocaleString("en-US")} 張影像。</p>}{system.isError && <p className="field-error" role="alert">無法取得 Backend 上傳限制；請重試連線後再建立檢測。</p>}</section>
      <footer className="form-actions"><p><strong>資料邊界：</strong>上傳檔案只保存在設定的本機 artifact store。</p><button className="button" disabled={!valid || create.isPending}>{create.isPending ? "正在建立檢測…" : "開始檢測"}</button></footer>{create.isError && <p className="field-error" role="alert">無法建立批次。請檢查檔案後再試一次。</p>}</form>
  </div>;
}
