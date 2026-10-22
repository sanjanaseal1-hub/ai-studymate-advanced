// The only place that talks to the backend. Throws Error(userFriendlyMessage) on failure.
export const BASE_URL = import.meta.env.VITE_API_URL || ""; // empty = use the Vite dev proxy

// json: object sent as JSON | form: FormData (file uploads). Returns the parsed JSON body.
export async function request(path, { method = "POST", json, form, timeout = 60000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: json ? { "Content-Type": "application/json" } : undefined,
      body: form ?? (json ? JSON.stringify(json) : undefined),
      signal: controller.signal,
    });
    let data = null;
    try { data = await response.json(); } catch { /* not JSON */ }
    if (!response.ok || !data?.success) {
      throw new Error(data?.error || "Unable to complete the request right now. Please try again.");
    }
    return data;
  } catch (err) {
    if (err.name === "AbortError") throw new Error("The request took too long. Please try again.");
    if (err instanceof TypeError) throw new Error("Cannot reach the server. Check your connection and try again.");
    throw err; // already a friendly Error from above
  } finally {
    clearTimeout(timer);
  }
}

// Study utilities (summarize, quiz, explain, improve-answer)
export async function generate(endpoint, content, options) {
  return (await request(`/api/${endpoint}`, { json: { content, options } })).result;
}
