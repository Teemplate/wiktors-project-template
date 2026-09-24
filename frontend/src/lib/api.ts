// Empty in every environment: nginx (prod, e2e) and the Vite proxy (dev) both
// serve the API from the same origin. See vite.config.ts and nginx/snippets/.
export const API_BASE = import.meta.env.VITE_API_BASE ?? "";
