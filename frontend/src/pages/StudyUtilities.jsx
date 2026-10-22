import { useState } from "react";
import UtilityCards from "../components/UtilityCards";
import StudyForm from "../components/StudyForm";
import ResultView from "../components/ResultView";
import { UTILITIES } from "../utilities";
import { generate } from "../services/api";
import { buildOptions, validateInput } from "../utils/validation";

const defaultsFor = (utility) => Object.fromEntries(utility.options.filter((f) => f.default !== undefined).map((f) => [f.name, f.default]));

export default function StudyUtilities() {
  const [selectedId, setSelectedId] = useState(null);
  const [content, setContent] = useState("");
  const [options, setOptions] = useState({});
  const [status, setStatus] = useState("idle"); // idle | loading | success | error
  const [result, setResult] = useState("");
  const [message, setMessage] = useState(""); // validation or API error text

  const utility = UTILITIES.find((u) => u.id === selectedId);
  const loading = status === "loading";

  function selectUtility(id) {
    setSelectedId(id);
    setContent("");
    setOptions(defaultsFor(UTILITIES.find((u) => u.id === id)));
    setStatus("idle"); setResult(""); setMessage("");
  }

  async function handleSubmit() {
    if (loading) return; // prevents duplicate requests
    const problem = validateInput(content, options, utility);
    if (problem) { setMessage(problem); setStatus("idle"); return; } // nothing is sent to the API
    setMessage(""); setStatus("loading");
    try {
      setResult(await generate(utility.endpoint, content, buildOptions(options, utility)));
      setStatus("success");
    } catch (err) {
      setMessage(err.message); setStatus("error");
    }
  }

  return (
    <>
      <UtilityCards selectedId={selectedId} onSelect={selectUtility} disabled={loading} />

        {!utility && <p className="empty">Choose a tool above to get started: summarize notes, make a quiz, explain a concept, or improve an answer.</p>}

        {utility && status !== "success" && (
          <StudyForm utility={utility} content={content} options={options}
            onContentChange={setContent} onOptionChange={(name, v) => setOptions((o) => ({ ...o, [name]: v }))}
            onSubmit={handleSubmit} loading={loading} validationError={message} />
        )}

        {loading && <p className="loading" role="status">AI is generating your response...</p>}

        {status === "success" && <ResultView result={result} onReset={() => selectUtility(selectedId)} />}
    </>
  );
}
