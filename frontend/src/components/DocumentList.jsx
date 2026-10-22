const LABELS = { uploading: "Uploading", queued: "Queued", processing: "Processing", indexed: "Indexed", failed: "Failed" };

// Server documents + transient local rows (uploading / rejected). Each row shows its own status.
export default function DocumentList({ documents, local, selected, onToggle, onDelete, onRetry, busy }) {
  if (!documents.length && !local.length) return <p className="empty">No documents yet. Upload a file to get started.</p>;
  return (
    <ul className="doclist" aria-label="Documents">
      {local.map((r, i) => (
        <li key={`local-${i}`}>
          <span className={`badge ${r.state === "uploading" ? "info" : "low"}`}>{LABELS[r.state] || "Failed"}</span>
          <span className="docname">{r.name}</span>
          {r.error && <span className="rowerror">{r.error}</span>}
        </li>
      ))}
      {documents.map((d) => (
        <li key={d.id}>
          <input type="checkbox" aria-label={`Search only in ${d.filename}`} disabled={d.status !== "indexed"}
            checked={selected.includes(d.id)} onChange={() => onToggle(d.id)} />
          <span className={`badge ${d.status === "indexed" ? "ok" : d.status === "failed" ? "low" : "info"}`}>{LABELS[d.status]}</span>
          <span className="docname">{d.filename}</span>
          <span className="muted small">
            {d.file_type.toUpperCase()}
            {d.status === "indexed" && ` · ${d.chunks} chunks${d.file_type === "pdf" && d.pages > 1 ? ` · ${d.pages} pages` : ""}`}
            {d.duplicate && " · already uploaded"}
          </span>
          {d.status === "failed" && d.error && <span className="rowerror">{d.error}</span>}
          <span className="rowactions">
            {d.status === "failed" && <button type="button" className="link" onClick={() => onRetry(d.id)} disabled={busy}>Retry</button>}
            <button type="button" className="link danger" onClick={() => onDelete(d.id)} disabled={busy || d.status === "processing"}
              aria-label={`Delete ${d.filename}`}>Delete</button>
          </span>
        </li>
      ))}
    </ul>
  );
}
