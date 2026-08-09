import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateJob } from "../api/queries";
import { UploadDropzone } from "../components/UploadDropzone";
import { UploadManifest } from "../components/UploadManifest";

const categories = ["can", "fabric", "fruit_jelly", "rice", "sheet_metal", "vial", "wallplugs", "walnuts"];

export function NewInspection() {
  const [category, setCategory] = useState("can");
  const [files, setFiles] = useState<File[]>([]);
  const create = useCreateJob();
  const navigate = useNavigate();
  const valid = files.length > 0 && files.length <= 2_000 && files.every((file) => file.size <= 25 * 1024 * 1024);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid || create.isPending) return;
    const result = await create.mutateAsync({ category, files });
    navigate(`/jobs/${result.id}`, { state: { queuedCount: result.image_count } });
  }
  return <div className="page page--narrow"><header className="page-header"><div><span className="eyebrow">Secure batch intake</span><h1>New inspection</h1><p className="lede">Submit product images for anomaly scoring. Model outcomes are evidence for review, never automatic final rejection.</p></div></header>
    <form className="intake" onSubmit={submit}><section className="panel"><div className="field"><label htmlFor="component-category">Component category</label><select id="component-category" value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((value) => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select><small>The active frozen champion is selected for this category.</small></div><UploadDropzone files={files} onChange={setFiles} /><UploadManifest files={files} onRemove={(index) => setFiles(files.filter((_, candidate) => candidate !== index))} />{!valid && files.length > 0 && <p className="field-error" role="alert">Each file must be 25 MB or smaller and the batch may contain at most 2,000 images.</p>}</section>
      <footer className="form-actions"><p><strong>Data boundary:</strong> uploads remain in the configured local artifact store.</p><button className="button" disabled={!valid || create.isPending}>{create.isPending ? "Creating inspection…" : "Start inspection"}</button></footer>{create.isError && <p className="field-error" role="alert">The batch was not created. Check the files and try again.</p>}</form>
  </div>;
}
