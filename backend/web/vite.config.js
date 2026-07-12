import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev server proxies API + WebSocket to the FastAPI backend on :9000 so the
// dashboard talks to the *same* endpoints in dev as it will in production
// (where FastAPI serves this app's built `dist/` directly). No code changes
// between dev and the venue box.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/ws": { target: "ws://localhost:9000", ws: true },
      "/sos": "http://localhost:9000",
      "/inject": "http://localhost:9000",
      "/accept": "http://localhost:9000",
      "/transcribe": "http://localhost:9000",
      "/voice_sos": "http://localhost:9000",
      "/vtiles": "http://localhost:9000",
      "/basemaps-assets": "http://localhost:9000",
      "/static": "http://localhost:9000",
      "/queue": "http://localhost:9000",
      "/health": "http://localhost:9000",
    },
  },
  // Emit into ../static-dist so FastAPI can serve it without a build step at the venue.
  build: { outDir: "dist", emptyOutDir: true },
});
