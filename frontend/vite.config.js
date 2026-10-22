import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, "/api" requests are forwarded to the FastAPI backend.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "jsdom", setupFiles: "./src/test/setup.js", globals: true },
});
