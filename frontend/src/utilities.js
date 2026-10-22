// Each utility = one backend endpoint + the form fields it needs.
export const UTILITIES = [
  {
    id: "summarize", icon: "📚", name: "Summarize Notes", cardText: "Turn long notes into concise revision material.",
    endpoint: "summarize", title: "Summarize notes",
    description: "Paste your notes below and AI will convert them into a concise study summary.",
    inputLabel: "Your notes", placeholder: "Paste lecture notes or textbook paragraphs here…",
    button: "Generate Summary", options: [],
  },
  {
    id: "quiz", icon: "📝", name: "Generate Quiz", cardText: "Create practice MCQs from your notes.",
    endpoint: "quiz", title: "Generate a quiz",
    description: "Paste your notes and AI will write multiple-choice questions based only on them.",
    inputLabel: "Your notes or topic text", placeholder: "Paste the material you want to be quizzed on…",
    button: "Generate Quiz",
    options: [
      { name: "num_questions", label: "Number of questions", type: "number", min: 1, max: 10, default: 5 },
      { name: "difficulty", label: "Difficulty", type: "select", choices: ["easy", "medium", "hard"], default: "medium" },
      { name: "topic", label: "Topic (optional)", type: "text", placeholder: "e.g. Mitosis" },
    ],
  },
  {
    id: "explain", icon: "💡", name: "Explain Concept", cardText: "Understand difficult concepts in simple language.",
    endpoint: "explain", title: "Explain a concept",
    description: "Type a concept or question and AI will explain it step by step with an example.",
    inputLabel: "Concept or question", placeholder: "e.g. What is a binary search tree?",
    button: "Explain Concept",
    options: [{ name: "level", label: "Level", type: "select", choices: ["beginner", "intermediate", "advanced"], default: "beginner" }],
  },
  {
    id: "improve", icon: "✍️", name: "Improve Answer", cardText: "Convert your rough answer into a clearer answer.",
    endpoint: "improve-answer", title: "Improve an answer",
    description: "Paste your answer and AI will rewrite it more clearly without changing your meaning.",
    inputLabel: "Your original answer", placeholder: "Paste the answer you wrote…",
    button: "Improve Answer",
    options: [{ name: "subject", label: "Subject (optional)", type: "text", placeholder: "e.g. Biology" }],
  },
];
