import { useRef, useState } from "react";
import { SUPPORTED_LABEL } from "../utils/validation";

// Drag-and-drop or file-picker. Calls onFiles(File[]); the parent validates and uploads.
export default function UploadPanel({ onFiles, disabled }) {
  const input = useRef(null);
  const [dragging, setDragging] = useState(false);
  const pick = (list) => { if (list.length) onFiles(Array.from(list)); if (input.current) input.current.value = ""; };
  return (
    <div className={`dropzone ${dragging ? "dragging" : ""}`}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); if (!disabled) pick(e.dataTransfer.files); }}>
      <p><strong>Drag and drop files here</strong> or</p>
      <label htmlFor="files" className="secondary filebtn">Choose files</label>
      <input id="files" ref={input} type="file" multiple accept=".pdf,.txt,.md,.markdown" className="visually-hidden"
        onChange={(e) => pick(e.target.files)} disabled={disabled} />
      <p className="muted small">Supported: {SUPPORTED_LABEL}. Up to 5 files, 10 MB each.</p>
    </div>
  );
}
