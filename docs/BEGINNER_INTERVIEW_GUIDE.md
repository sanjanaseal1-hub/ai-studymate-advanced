# Interview Guide (personal prep)

## Understand before presenting
1. **Request path:** React → `api.js` → FastAPI route → Pydantic validation → prompt builder → `GeminiClient` → Gemini → response check → JSON → React renders Markdown.
2. **Why a backend:** keeps the API key secret and validates input.
3. **Prompt structure:** Role (system instruction) + Task + Input (delimited) + Requirements + Output format. Open `prompts/templates.py` and explain each part.
4. **Errors:** `LLMError(status, user_message, log_detail)`; handlers return only `user_message`.
5. **Provider swap:** abstract `LLMClient`; only `get_llm_client()` changes.
6. **Limits:** depends on model accuracy; no auth, history or rate limiting yet.

## Likely questions
- **Why not just a chatbot?** Fixed workflows with tuned prompts give consistent, task-fit output and need no prompting skill.
- **Where is the API key and why?** `.env`, read only by the backend; a key in frontend code is visible to anyone.
- **Why validate twice?** Frontend for quick feedback; backend because the API can be called directly.
- **How do you reduce hallucination?** "Use only the material" constraints, low temperature, quiz limited to supplied text, improver told not to add facts.
- **What is prompt injection and what did you do?** Pasted text may contain instructions. Input is wrapped in tags and the role says to treat it as data. This reduces, not removes, the risk.
- **Rate limit or timeout?** Mapped to 429 / 504 with friendly messages; 45 s timeout; the user's text is kept for retry.
- **Unexpected Gemini output?** `extract_text` checks JSON shape and empty text, raising a 502 `LLMError`.
- **Changing provider?** Implement `LLMClient.generate` for the new provider and return it from `get_llm_client`.
- **Why Pydantic?** Declarative validation, automatic 422s, typed request models.
- **Preventing double submits?** A `status === "loading"` guard in the handler plus a disabled button.
- **How is output made readable?** Prompts demand Markdown sections; `react-markdown` renders them safely.
- **Next improvements?** PDF upload, scored quizzes, history, auth, per-user rate limits, streaming.
- **How did you test without the API?** FastAPI dependency override with a fake client; real calls checked manually.
