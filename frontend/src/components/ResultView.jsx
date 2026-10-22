import { useState } from "react";
import ReactMarkdown from "react-markdown";

// react-markdown renders headings, lists and bold text safely (it does not run raw HTML).
export default function ResultView({ result, onReset }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(result); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* ignore */ }
  };
  return (
    <section className="panel result" aria-live="polite">
      <div className="result-bar">
        <h2>Result</h2>
        <div>
          <button type="button" className="secondary" onClick={copy}>{copied ? "Copied" : "Copy"}</button>{" "}
          <button type="button" className="secondary" onClick={onReset}>Start another task</button>
        </div>
      </div>
      <div className="markdown"><ReactMarkdown>{result}</ReactMarkdown></div>
    </section>
  );
}
