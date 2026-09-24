import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Set by compose/web.dev.with-api.yml when the project has the api block. A
// web-only project has no /api to proxy, and an unconditional proxy would turn
// every mistaken /api call into a confusing ECONNREFUSED instead of a 404.
const apiTarget = process.env.API_PROXY_TARGET;

export default defineConfig({
  // "/" for a custom domain. A GitHub Pages project site is served under
  // /<repo>/, so .github/workflows/pages.yml sets VITE_BASE for that case.
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // In local dev the SPA and the API are on different ports. Proxying /api
    // keeps the frontend code identical to production, where nginx serves both
    // from one origin — so VITE_API_BASE can stay empty everywhere and there
    // is no CORS hole to open.
    proxy: apiTarget ? { "/api": { target: apiTarget, changeOrigin: true } } : undefined,
  },
});
