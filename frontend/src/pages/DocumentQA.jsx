import { useCallback, useEffect, useRef, useState } from "react";
import AnswerView from "../components/AnswerView";
import Diagnostics from "../components/Diagnostics";
import DocumentList from "../components/DocumentList";
import SourceCards from "../components/SourceCards";
import UploadPanel from "../components/UploadPanel";
import { deleteDocument, listDocuments, reindexDocument, streamQuestion, uploadDocuments } from "../services/ragApi";
import { splitFiles, validateQuestion } from "../utils/validation";

const POLL_MS = 1500;
const STEPS = [["embedding", "Embedding question"], ["retrieving", "Retrieving documents"], ["reranking", "Re-ranking evidence"],
  ["generating", "Generating grounded answer"], ["validating", "Validating citations"]];

export default function DocumentQA() {
  const [documents, setDocuments] = useState([]);
  const [local, setLocal] = useState([]);       // rows that exist only in the browser: uploading / rejected
  const [selected, setSelected] = useState([]); // document ids to restrict the search to (empty = all)
  const [message, setMessage] = useState("");
  const [question, setQuestion] = useState("");
  const [questionError, setQuestionError] = useState("");
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(null);
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState(null);
  const [highlight, setHighlight] = useState(null);
  const abortRef = useRef(null);

  const refresh = useCallback(() => listDocuments().then(setDocuments).catch(() => {}), []);
  useEffect(() => { refresh(); }, [refresh]);

  const inProgress = documents.some((d) => d.status === "queued" || d.status === "processing");
  useEffect(() => { // poll indexing status while any document is still being processed
    if (!inProgress) return undefined;
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [inProgress, refresh]);

  const indexed = documents.filter((d) => d.status === "indexed");
  const effectiveSelected = selected.filter((id) => indexed.some((d) => d.id === id));

  async function handleFiles(files) {
    const { ok, rejected } = splitFiles(files);
    setMessage("");
    setLocal([...rejected.map((r) => ({ state: "failed", ...r })), ...ok.map((f) => ({ state: "uploading", name: f.name }))]);
    if (!ok.length) return;
    try {
      const res = await uploadDocuments(ok);
      setLocal([...rejected.map((r) => ({ state: "failed", ...r })), ...res.errors.map((e) => ({ state: "failed", name: e.filename, error: e.error }))]);
    } catch (err) {
      setLocal([...rejected.map((r) => ({ state: "failed", ...r })), ...ok.map((f) => ({ state: "failed", name: f.name, error: err.message }))]);
    }
    refresh();
  }

  const act = (fn) => async (id) => { setMessage(""); try { await fn(id); setResult(null); } catch (err) { setMessage(err.message); } refresh(); };
  const handleDelete = act((id) => deleteDocument(id));
  const handleRetry = act((id) => reindexDocument(id));
  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  async function ask() {
    if (running) return;
    const problem = validateQuestion(question);
    if (problem) { setQuestionError(problem); return; }
    setQuestionError(""); setRunning(true); setResult(null); setDraft(""); setStage(null); setHighlight(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamQuestion(question, effectiveSelected.length ? effectiveSelected : undefined, {
        signal: controller.signal, onStage: (s) => setStage(s.stage), onToken: (t) => setDraft((d) => d + t.text), onResult: setResult,
      });
    } catch (err) {
      if (err.name !== "AbortError") setQuestionError(err.message);
    } finally { setRunning(false); setStage(null); abortRef.current = null; }
  }

  return (
    <>
      <section className="panel">
        <h2>1. Upload documents</h2>
        <p className="muted">Files are validated, split into chunks, embedded and stored in a persistent vector index. This keeps running in the background.</p>
        <UploadPanel onFiles={handleFiles} disabled={false} />
        {message && <p className="error" role="alert">{message}</p>}
        <DocumentList documents={documents} local={local} selected={effectiveSelected} onToggle={toggle}
          onDelete={handleDelete} onRetry={handleRetry} busy={false} />
        {indexed.length > 1 && <p className="muted small">Tick documents to search only those; leave all unticked to search everything.</p>}
      </section>

      <section className="panel">
        <h2>2. Ask a question</h2>
        {indexed.length === 0 && <p className="empty">Upload a document and wait until it shows “Indexed” to start asking questions.</p>}
        <label htmlFor="question">Your question</label>
        <input id="question" type="text" value={question} placeholder="e.g. What is DNA replication?"
          onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} disabled={running || indexed.length === 0} />
        {questionError && <p className="error" role="alert">{questionError}</p>}
        <div className="actions">
          <button type="button" className="primary" onClick={ask} disabled={running || indexed.length === 0}>{running ? "Working…" : "Ask Question"}</button>
          {running && <button type="button" className="secondary" onClick={() => abortRef.current?.abort()}>Stop</button>}
        </div>
        {running && (
          <ol className="steps" role="status" aria-label="Progress">
            {STEPS.map(([id, label], i) => {
              const current = STEPS.findIndex(([s]) => s === stage);
              return <li key={id} className={i < current ? "done" : i === current ? "active" : ""}>{label}</li>;
            })}
          </ol>
        )}
      </section>

      {running && draft && <AnswerView answer={draft} streaming />}
      {result && (
        <>
          <AnswerView answer={result.answer} state={result.state} confidence={result.confidence} warnings={result.warnings} onCite={setHighlight} />
          <SourceCards sources={result.sources} highlight={highlight} />
          <Diagnostics diagnostics={result.retrieval_diagnostics} sources={result.sources} />
        </>
      )}
    </>
  );
}
