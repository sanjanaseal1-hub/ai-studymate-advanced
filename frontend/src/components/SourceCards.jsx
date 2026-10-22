import { useEffect, useState } from "react";

const GROUPS = [
  { status: "used", title: "Used as context", help: "Sent to the AI after the relevance threshold and re-ranking." },
  { status: "excluded", title: "Retrieved but excluded", help: "Passed the threshold but ranked below the final top results." },
  { status: "below_threshold", title: "Below relevance threshold", help: "Too dissimilar to the question, so never sent to the AI." },
];
const where = (s) => (s.page ? `Page ${s.page}` : s.heading ? `Section: ${s.heading}` : `Chunk ${s.chunk_index + 1}`);
const fmt = (n) => (n === null || n === undefined ? "–" : n.toFixed(2));

export default function SourceCards({ sources, highlight }) {
  const [open, setOpen] = useState(new Set());
  useEffect(() => { // a clicked citation opens, scrolls to and highlights its card
    if (!highlight) return;
    const card = sources.find((s) => s.citation === highlight);
    if (!card) return;
    setOpen((prev) => new Set(prev).add(card.rank));
    document.getElementById(`source-${card.rank}`)?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [highlight, sources]);
  const toggle = (rank, isOpen) => setOpen((prev) => { const next = new Set(prev); isOpen ? next.add(rank) : next.delete(rank); return next; });

  return (
    <section className="panel sources" aria-label="Retrieved sources">
      <h2>Sources</h2>
      {GROUPS.map(({ status, title, help }) => {
        const items = sources.filter((s) => s.status === status);
        if (!items.length) return null;
        return (
          <div key={status} className="sourcegroup">
            <h3>{title} <span className="muted small">({items.length}) · {help}</span></h3>
            {items.map((s) => (
              <details key={s.rank} id={`source-${s.rank}`} open={open.has(s.rank)} onToggle={(e) => toggle(s.rank, e.target.open)}
                className={`source ${status !== "used" ? "unused" : ""} ${highlight && s.citation === highlight ? "highlight" : ""}`}>
                <summary>
                  {s.citation && <span className="citebadge">[{s.citation}]</span>}
                  <strong>{s.document}</strong> · {where(s)} · chunk {s.chunk_index + 1}
                  {s.cited && <span className="badge ok">cited in answer</span>}
                  <span className="score">
                    similarity {fmt(s.vector_score)}{s.final_score !== null && ` · re-ranked ${fmt(s.final_score)}`}
                  </span>
                </summary>
                {s.final_score !== null && (
                  <p className="muted small">Vector similarity {fmt(s.vector_score)} · keyword (BM25) {fmt(s.lexical_score)} · final score {fmt(s.final_score)}</p>
                )}
                <div className="bar" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(1, s.vector_score)) * 100}%` }} /></div>
                <blockquote>{s.text}</blockquote>
              </details>
            ))}
          </div>
        );
      })}
    </section>
  );
}
