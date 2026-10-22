import { BASE_URL, request } from "./api";
import { parseSSE } from "./sse";

export const listDocuments = async () => (await request("/api/documents", { method: "GET" })).documents;

export async function uploadDocuments(files) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  return request("/api/documents/upload", { form, timeout: 120000 }); // 202: {documents, errors}; indexing runs in the background
}

export const reindexDocument = (id, force = false) => request(`/api/documents/${id}/index${force ? "?force=true" : ""}`);
export const deleteDocument = (id) => request(`/api/documents/${id}`, { method: "DELETE" });

// Plain (non-streaming) answer; kept for API completeness and as a fallback.
export const askQuestion = (question, documentIds) => request("/api/qa", { json: { question, document_ids: documentIds } });

/**
 * Stream an answer over SSE. Calls onStage({stage,message}), onToken({text}), onResult(result).
 * Throws Error(friendly message) on failure; throws an AbortError if `signal` is aborted (Stop button).
 */
export async function streamQuestion(question, documentIds, { onStage, onToken, onResult, signal }) {
  let response;
  try {
    response = await fetch(`${BASE_URL}/api/qa/stream`, {
      method: "POST", headers: { "Content-Type": "application/json" }, signal,
      body: JSON.stringify({ question, document_ids: documentIds }),
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new Error("Cannot reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    let data = null;
    try { data = await response.json(); } catch { /* not JSON */ }
    throw new Error(data?.error || "Unable to complete the request right now. Please try again.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let gotResult = false;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSSE(buffer);
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      if (event === "stage") onStage?.(data);
      else if (event === "token") onToken?.(data);
      else if (event === "result") { gotResult = true; onResult?.(data); }
      else if (event === "error") throw new Error(data.error || "Something went wrong. Please try again.");
    }
  }
  if (!gotResult) throw new Error("The answer stream ended unexpectedly. Please try again.");
}
