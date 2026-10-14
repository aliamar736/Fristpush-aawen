import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// GitHub Codespaces serves the app from *.app.github.dev; allow that host only there.
const allowedHosts = process.env.CODESPACES ? true : undefined;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts,
    proxy: { "/api": { target: process.env.AAWEN_API ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
  preview: {
    port: 4173,
    allowedHosts,
    proxy: { "/api": { target: process.env.AAWEN_API ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { target: "es2019", sourcemap: false, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"], include: ["src/**/*.test.{ts,tsx}"] },
});
