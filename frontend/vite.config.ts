import path from "node:path"
import react from "@vitejs/plugin-react"
/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config"

// The API base is read from VITE_API_BASE at build time (default: the local backend).
// In dev, /api is proxied to the FastAPI server so the app can run without CORS.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
})
