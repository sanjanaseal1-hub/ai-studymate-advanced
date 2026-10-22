import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import App from "./App";
import * as api from "./services/api";

vi.mock("./services/api");

async function openSummarizer() {
  render(<App />);
  await userEvent.click(screen.getByRole("tab", { name: /study utilities/i }));
  await userEvent.click(screen.getByRole("button", { name: /summarize notes/i }));
}

describe("AI StudyMate", () => {
  beforeEach(() => vi.resetAllMocks());

  it("shows the four utilities", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("tab", { name: /study utilities/i }));
    ["Summarize Notes", "Generate Quiz", "Explain Concept", "Improve Answer"].forEach((n) =>
      expect(screen.getByRole("button", { name: new RegExp(n, "i") })).toBeInTheDocument());
  });

  it("blocks empty and whitespace-only input without calling the API", async () => {
    await openSummarizer();
    await userEvent.type(screen.getByLabelText(/your notes/i), "   ");
    await userEvent.click(screen.getByRole("button", { name: /generate summary/i }));
    expect(screen.getByRole("alert")).toHaveTextContent("Please enter some study material first.");
    expect(api.generate).not.toHaveBeenCalled();
  });

  it("sends valid input and displays the formatted result", async () => {
    api.generate.mockResolvedValue("## Topic\nPhotosynthesis\n- Light reactions");
    await openSummarizer();
    await userEvent.type(screen.getByLabelText(/your notes/i), "Plants make glucose.");
    await userEvent.click(screen.getByRole("button", { name: /generate summary/i }));
    expect(await screen.findByRole("heading", { name: "Topic" })).toBeInTheDocument();
    expect(api.generate).toHaveBeenCalledWith("summarize", "Plants make glucose.", {});
  });

  it("shows a loading state and disables the button while waiting", async () => {
    let finish;
    api.generate.mockReturnValue(new Promise((r) => { finish = r; }));
    await openSummarizer();
    await userEvent.type(screen.getByLabelText(/your notes/i), "Some notes");
    await userEvent.click(screen.getByRole("button", { name: /generate summary/i }));
    expect(screen.getByText("AI is generating your response...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /working/i })).toBeDisabled();
    finish("done");
    await waitFor(() => expect(screen.queryByText(/AI is generating/)).not.toBeInTheDocument());
  });

  it("displays a friendly API error and keeps the user's text", async () => {
    api.generate.mockRejectedValue(new Error("Too many requests right now. Please wait a moment and try again."));
    await openSummarizer();
    await userEvent.type(screen.getByLabelText(/your notes/i), "Some notes");
    await userEvent.click(screen.getByRole("button", { name: /generate summary/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/too many requests/i);
    expect(screen.getByLabelText(/your notes/i)).toHaveValue("Some notes");
  });
});
