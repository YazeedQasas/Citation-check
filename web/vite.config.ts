import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the interface runs on :5173 and forwards /api to the Python API on :8000 (python -m citation_check serve).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
});
