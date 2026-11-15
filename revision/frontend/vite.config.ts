import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En développement, l'API tourne à part (uvicorn) ; en usage normal, FastAPI sert le dossier dist.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
});
