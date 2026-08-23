import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // In local dev the SPA and the API are on different ports. Proxying /api
    // keeps the frontend code identical to production, where the shared Caddy
    // serves both from one origin — so VITE_API_BASE can stay empty everywhere
    // and there is no CORS hole to open.
    proxy: {
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});
