import { MAX_CONTENT_CHARS } from "../utils/validation";

export default function StudyForm({ utility, content, options, onContentChange, onOptionChange, onSubmit, loading, validationError }) {
  return (
    <form className="panel" onSubmit={(e) => { e.preventDefault(); onSubmit(); }} noValidate>
      <h2>{utility.title}</h2>
      <p className="muted">{utility.description}</p>

      <label htmlFor="content">{utility.inputLabel}</label>
      <textarea id="content" rows={9} value={content} placeholder={utility.placeholder}
        onChange={(e) => onContentChange(e.target.value)} disabled={loading} />
      <div className={`counter ${content.length > MAX_CONTENT_CHARS ? "over" : ""}`}>{content.length} / {MAX_CONTENT_CHARS}</div>

      {utility.options.length > 0 && (
        <div className="options">
          {utility.options.map((f) => (
            <div key={f.name} className="option">
              <label htmlFor={f.name}>{f.label}</label>
              {f.type === "select" ? (
                <select id={f.name} value={options[f.name] ?? ""} onChange={(e) => onOptionChange(f.name, e.target.value)} disabled={loading}>
                  {f.choices.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              ) : (
                <input id={f.name} type={f.type} min={f.min} max={f.max} placeholder={f.placeholder}
                  value={options[f.name] ?? ""} onChange={(e) => onOptionChange(f.name, e.target.value)} disabled={loading} />
              )}
            </div>
          ))}
        </div>
      )}

      {validationError && <p className="error" role="alert">{validationError}</p>}

      <button type="submit" className="primary" disabled={loading}>{loading ? "Working…" : utility.button}</button>
    </form>
  );
}
