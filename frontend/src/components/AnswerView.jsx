import ReactMarkdown from "react-markdown";

const STATE = {
  grounded: { text: "Grounded in your documents", cls: "ok" },
  insufficient: { text: "Not enough information in your documents", cls: "low" },
  ungrounded: { text: "No verifiable citations: treat with caution", cls: "warn" },
  no_evidence: { text: "No relevant evidence found", cls: "low" },
};

// Turn [1] / [1, 2] into clickable links that scroll to the matching source card.
export const linkCitations = (text) =>
  text.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_, nums) => nums.split(",").map((n) => `[[${n.trim()}]](#cite-${n.trim()})`).join(""));

export default function AnswerView({ answer, state, confidence, warnings = [], onCite, streaming = false }) {
  const meta = STATE[state];
  return (
    <section className="panel result" aria-live="polite">
      <h2>
        Answer {streaming && <span className="badge info">generating…</span>}
        {meta && <span className={`badge ${meta.cls}`}>{meta.text}</span>}
        {confidence && confidence.label !== "none" && <span className="badge info" title="Heuristic based on source similarity and citation coverage">confidence: {confidence.label}</span>}
      </h2>
      {state === "no_evidence" || state === "insufficient" ? <p className="notice-state">{answer}</p> : null}
      {state !== "no_evidence" && state !== "insufficient" && (
        <div className="markdown">
          <ReactMarkdown components={{
            a: ({ href, children }) => href?.startsWith("#cite-")
              ? <button type="button" className="cite" onClick={() => onCite?.(Number(href.slice(6)))} aria-label={`Show source ${href.slice(6)}`}>{children}</button>
              : <a href={href} target="_blank" rel="noreferrer">{children}</a>,
          }}>{linkCitations(answer)}</ReactMarkdown>
        </div>
      )}
      {warnings.map((w) => <p key={w} className="warning" role="note">⚠ {w}</p>)}
    </section>
  );
}
