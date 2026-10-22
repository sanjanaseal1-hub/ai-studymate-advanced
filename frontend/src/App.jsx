import { useState } from "react";
import DocumentQA from "./pages/DocumentQA";
import StudyUtilities from "./pages/StudyUtilities";

const TABS = [
  { id: "docs", label: "Document Q&A" },
  { id: "study", label: "Study Utilities" },
];

export default function App() {
  const [tab, setTab] = useState("docs");
  return (
    <div className="app">
      <header>
        <h1>AI StudyMate</h1>
        <p>Your AI-powered study assistant</p>
      </header>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id}
            className={tab === t.id ? "tab active" : "tab"} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      <main>{tab === "docs" ? <DocumentQA /> : <StudyUtilities />}</main>
    </div>
  );
}
