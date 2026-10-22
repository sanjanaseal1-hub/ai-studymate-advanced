// Frontend validation: quick feedback. The backend validates again.
export const MAX_CONTENT_CHARS = 8000;

export function validateInput(content, options, utility) {
  if (!content.trim()) return "Please enter some study material first.";
  if (content.length > MAX_CONTENT_CHARS)
    return `Your text is too long. Please keep it under ${MAX_CONTENT_CHARS} characters.`;
  for (const field of utility.options) {
    const value = options[field.name];
    if (field.type === "number") {
      const n = Number(value);
      if (!Number.isInteger(n) || n < field.min || n > field.max)
        return `${field.label} must be a whole number from ${field.min} to ${field.max}.`;
    }
    if (field.type === "select" && !field.choices.includes(value)) return `Please choose a valid ${field.label.toLowerCase()}.`;
  }
  return null;
}

// Build the request body: numbers become numbers, empty optional fields are dropped.
export function buildOptions(options, utility) {
  const out = {};
  for (const field of utility.options) {
    const value = options[field.name];
    if (value === undefined || String(value).trim() === "") continue;
    out[field.name] = field.type === "number" ? Number(value) : String(value).trim();
  }
  return out;
}

// ---- Document Q&A validation (the backend checks everything again) ----
export const MAX_FILE_MB = 10;
export const MAX_FILES = 5;
export const MAX_QUESTION_CHARS = 1000;
export const SUPPORTED_LABEL = "PDF, TXT or Markdown (.md)";

export function checkFile(file) {
  if (!/\.(txt|pdf|md|markdown)$/i.test(file.name)) return `'${file.name}' is not supported. Please upload ${SUPPORTED_LABEL} files only.`;
  if (file.size === 0) return `'${file.name}' is empty.`;
  if (file.size > MAX_FILE_MB * 1024 * 1024) return `'${file.name}' is too large. The limit is ${MAX_FILE_MB} MB per file.`;
  return null;
}

// Split a selection into files we can upload and files we reject immediately (each with a reason).
export function splitFiles(files) {
  const ok = [], rejected = [];
  files.forEach((f) => { const error = checkFile(f); (error ? rejected.push({ name: f.name, error }) : ok.push(f)); });
  if (ok.length > MAX_FILES) {
    ok.slice(MAX_FILES).forEach((f) => rejected.push({ name: f.name, error: `You can upload up to ${MAX_FILES} files at a time.` }));
    ok.length = MAX_FILES;
  }
  return { ok, rejected };
}

export function validateQuestion(question) {
  if (!question.trim()) return "Please enter a question first.";
  if (question.length > MAX_QUESTION_CHARS) return `Your question is too long. Please keep it under ${MAX_QUESTION_CHARS} characters.`;
  return null;
}
