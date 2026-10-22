import { useState } from "react";

export default function Diagnostics({ diagnostics: d, sources }) {
  const [show, setShow] = useState(false);
  return (
    <section className="panel">
      <button type="button" className="secondary" onClick={() => setShow(!show)} aria-expanded={show}>
        {show ? "Hide technical details" : "Show technical details"}
      </button>
      {show && (
        <div className="tech">
          <dl>
            <dt>Documents searched</dt><dd>{d.documents_searched}</dd>
            <dt>Chunks searched</dt><dd>{d.chunks_searched}</dd>
            <dt>Candidates retrieved</dt><dd>{d.candidates_retrieved} (of up to {d.candidate_k})</dd>
            <dt>Above threshold ({d.similarity_threshold})</dt><dd>{d.candidates_above_threshold}</dd>
            <dt>Chunks used (top {d.top_k})</dt><dd>{d.chunks_used}</dd>
            <dt>Re-rank weight</dt><dd>{d.rerank_alpha} vector + {(1 - d.rerank_alpha).toFixed(2)} keyword</dd>
            <dt>Timings (ms)</dt><dd>{Object.entries(d.timings_ms).map(([k, v]) => `${k} ${v}`).join(" · ")}</dd>
          </dl>
          <div className="tablewrap">
            <table>
              <thead><tr><th>#</th><th>Document</th><th>Vector</th><th>Keyword</th><th>Final</th><th>Status</th></tr></thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.rank}>
                    <td>{s.rank}</td><td>{s.document}</td><td>{s.vector_score.toFixed(3)}</td>
                    <td>{s.lexical_score?.toFixed(3) ?? "–"}</td><td>{s.final_score?.toFixed(3) ?? "–"}</td><td>{s.status.replace("_", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
