import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import App from "./App";
import { parseSSE } from "./services/sse";
import { linkCitations } from "./components/AnswerView";
import * as rag from "./services/ragApi";

vi.mock("./services/ragApi");

const doc = (over) => ({ id: "d1", filename: "Biology.pdf", file_type: "pdf", size_bytes: 10, status: "indexed", error: null, pages: 3, chunks: 7,
  characters: 5000, created_at: "", indexed_at: "", duplicate: false, ...over });
const source = (over) => ({ citation: 1, rank: 1, document_id: "d1", document: "Biology.pdf", file_type: "pdf", page: 3, heading: null, chunk_index: 2,
  vector_score: 0.87, lexical_score: 0.6, final_score: 0.79, status: "used", cited: true, text: "Helicase unwinds the helix.", ...over });
const RESULT = {
  success: true, answer: "DNA replication copies DNA [1].", state: "grounded", grounded: true, confidence: { score: 0.8, label: "high" },
  citations: [], warnings: ["Removed 1 invalid citation(s) that did not match any retrieved source."],
  sources: [source(), source({ citation: null, rank: 2, page: 1, chunk_index: 0, status: "excluded", cited: false, vector_score: 0.5, text: "Excluded text." }),
    source({ citation: null, rank: 3, status: "below_threshold", cited: false, vector_score: 0.2, lexical_score: null, final_score: null, text: "Weak text." })],
  retrieval_diagnostics: { documents_searched: 1, chunks_searched: 7, candidate_k: 15, top_k: 4, similarity_threshold: 0.5, rerank_alpha: 0.7,
    candidates_retrieved: 3, candidates_above_threshold: 2, chunks_used: 1, timings_ms: { embedding: 12 } },
};
const NO_EVIDENCE = { ...RESULT, answer: "I could not find sufficiently relevant information in the uploaded documents to answer this question.",
  state: "no_evidence", grounded: false, confidence: { score: 0, label: "none" }, warnings: [],
  sources: [source({ citation: null, status: "below_threshold", cited: false, vector_score: 0.2, final_score: null, lexical_score: null })] };

const streaming = (result) => async (q, ids, { onStage, onToken, onResult }) => {
  onStage({ stage: "embedding", message: "Embedding" });
  onToken({ text: "DNA " });
  onResult(result);
};

describe("Document Q&A (advanced)", () => {
  beforeEach(() => { vi.resetAllMocks(); rag.listDocuments.mockResolvedValue([]); });

  it("shows supported-file guidance and disables asking until a document is indexed", async () => {
    render(<App />);
    expect(screen.getByText(/PDF, TXT or Markdown/)).toBeInTheDocument();
    expect(await screen.findByText(/wait until it shows/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask question/i })).toBeDisabled();
  });

  it("rejects unsupported files immediately with a per-file reason and uploads nothing", async () => {
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/choose files/i), new File(["x"], "notes.docx"), { applyAccept: false });
    expect(await screen.findByText(/'notes.docx' is not supported/)).toBeInTheDocument();
    expect(rag.uploadDocuments).not.toHaveBeenCalled();
  });

  it("uploads valid files and shows server-side rejections per file", async () => {
    rag.uploadDocuments.mockResolvedValue({ documents: [], errors: [{ filename: "bad.pdf", error: "'bad.pdf' could not be read. The PDF may be corrupted." }] });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/choose files/i), [new File(["# hi"], "notes.md"), new File(["%PDF"], "bad.pdf")]);
    expect(await screen.findByText(/may be corrupted/)).toBeInTheDocument();
    expect(rag.uploadDocuments.mock.calls[0][0].map((f) => f.name)).toEqual(["notes.md", "bad.pdf"]);
  });

  it("shows queued, processing, indexed and failed statuses; retry and delete work", async () => {
    rag.listDocuments.mockResolvedValue([doc({ id: "q", filename: "q.txt", status: "queued" }), doc({ id: "p", filename: "p.md", status: "processing" }),
      doc({}), doc({ id: "f", filename: "f.pdf", status: "failed", error: "'f.pdf' is password-protected and cannot be read." })]);
    rag.reindexDocument.mockResolvedValue({}); rag.deleteDocument.mockResolvedValue({});
    render(<App />);
    const list = await screen.findByRole("list", { name: "Documents" });
    ["Queued", "Processing", "Indexed", "Failed"].forEach((s) => expect(within(list).getByText(s)).toBeInTheDocument());
    expect(within(list).getByText(/password-protected/)).toBeInTheDocument();
    expect(within(list).getByText(/7 chunks · 3 pages/)).toBeInTheDocument();
    await userEvent.click(within(list).getByRole("button", { name: "Retry" }));
    expect(rag.reindexDocument).toHaveBeenCalledWith("f");
    await userEvent.click(within(list).getByRole("button", { name: "Delete Biology.pdf" }));
    expect(rag.deleteDocument).toHaveBeenCalledWith("d1");
  });

  it("blocks an empty question", async () => {
    rag.listDocuments.mockResolvedValue([doc()]);
    render(<App />);
    await screen.findByText("Biology.pdf");
    await userEvent.click(screen.getByRole("button", { name: /ask question/i }));
    expect(screen.getByRole("alert")).toHaveTextContent("Please enter a question first.");
    expect(rag.streamQuestion).not.toHaveBeenCalled();
  });

  it("streams, then shows the validated answer, warnings, source groups, scores and diagnostics", async () => {
    rag.listDocuments.mockResolvedValue([doc()]);
    rag.streamQuestion.mockImplementation(streaming(RESULT));
    render(<App />);
    await screen.findByText("Biology.pdf");
    await userEvent.type(screen.getByLabelText(/your question/i), "What is DNA replication?");
    await userEvent.click(screen.getByRole("button", { name: /ask question/i }));
    expect(await screen.findByText(/DNA replication copies DNA/)).toBeInTheDocument();
    expect(rag.streamQuestion.mock.calls[0][1]).toBeUndefined();                // no document filter
    expect(screen.getByText("Grounded in your documents")).toBeInTheDocument();
    expect(screen.getByText(/Removed 1 invalid citation/)).toBeInTheDocument();
    expect(screen.getByText("Used as context")).toBeInTheDocument();
    expect(screen.getByText("Retrieved but excluded")).toBeInTheDocument();
    expect(screen.getByText("Below relevance threshold")).toBeInTheDocument();
    expect(screen.getByText(/similarity 0.87 · re-ranked 0.79/)).toBeInTheDocument();
    expect(screen.getByText("cited in answer")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /show technical details/i }));
    expect(screen.getByText(/Above threshold \(0.5\)/)).toBeInTheDocument();
  });

  it("clicking an inline citation highlights and opens the matching source card", async () => {
    rag.listDocuments.mockResolvedValue([doc()]);
    rag.streamQuestion.mockImplementation(streaming(RESULT));
    render(<App />);
    await screen.findByText("Biology.pdf");
    await userEvent.type(screen.getByLabelText(/your question/i), "q");
    await userEvent.click(screen.getByRole("button", { name: /ask question/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Show source 1" }));
    const card = document.getElementById("source-1");
    expect(card).toHaveClass("highlight");
    expect(card).toHaveAttribute("open");
    expect(screen.getByText("Helicase unwinds the helix.")).toBeVisible();
  });

  it("restricts the search to ticked documents", async () => {
    rag.listDocuments.mockResolvedValue([doc(), doc({ id: "d2", filename: "Genetics.txt", file_type: "txt" })]);
    rag.streamQuestion.mockImplementation(streaming(RESULT));
    render(<App />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /search only in genetics.txt/i }));
    await userEvent.type(screen.getByLabelText(/your question/i), "q");
    await userEvent.click(screen.getByRole("button", { name: /ask question/i }));
    await waitFor(() => expect(rag.streamQuestion.mock.calls[0][1]).toEqual(["d2"]));
  });

  it("shows a clear no-evidence state without citations", async () => {
    rag.listDocuments.mockResolvedValue([doc()]);
    rag.streamQuestion.mockImplementation(streaming(NO_EVIDENCE));
    render(<App />);
    await screen.findByText("Biology.pdf");
    await userEvent.type(screen.getByLabelText(/your question/i), "Who won the world cup?");
    await userEvent.click(screen.getByRole("button", { name: /ask question/i }));
    expect(await screen.findByText("No relevant evidence found")).toBeInTheDocument();
    expect(screen.getByText(/could not find sufficiently relevant/)).toBeInTheDocument();
    expect(screen.getByText("Below relevance threshold")).toBeInTheDocument();
    expect(screen.queryByText("Used as context")).not.toBeInTheDocument();
  });

  it("shows a friendly error when streaming fails", async () => {
    rag.listDocuments.mockResolvedValue([doc()]);
    rag.streamQuestion.mockRejectedValue(new Error("The AI took too long to respond. Please try again."));
    render(<App />);
    await screen.findByText("Biology.pdf");
    await userEvent.type(screen.getByLabelText(/your question/i), "Anything?");
    await userEvent.click(screen.getByRole("button", { name: /ask question/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/took too long/i));
  });
});

describe("helpers", () => {
  it("parses SSE events and keeps the unfinished remainder", () => {
    const { events, rest } = parseSSE('event: stage\ndata: {"stage":"embedding"}\n\nevent: token\ndata: {"text":"Hi"}\n\nevent: res');
    expect(events).toEqual([{ event: "stage", data: { stage: "embedding" } }, { event: "token", data: { text: "Hi" } }]);
    expect(rest).toBe("event: res");
  });
  it("turns citations into links", () => {
    expect(linkCitations("A [1] and B [2, 3].")).toBe("A [[1]](#cite-1) and B [[2]](#cite-2)[[3]](#cite-3).");
  });
});
