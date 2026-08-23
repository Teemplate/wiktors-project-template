import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Separate from vite.config.ts so the dev-server proxy block cannot affect the
// test run, and so `vitest` does not inherit a `server.port` that may be busy.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: false,
    // Playwright specs live in e2e/ and are run by scripts/e2e.sh, not vitest.
    // Without this, vitest picks them up and fails on the missing runner.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["./src/test-setup.ts"],
  },
});
