/**
 * Unit tests: fast, no browser, no backend. Each feature carries its own tests
 * next to it (features/<name>/*.test.tsx), so they leave with the feature.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { mockFetch } from "./test-utils";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the shell with whatever features this project has", () => {
    mockFetch(() => ({ message: "hi" }));
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 })).toBeTruthy();
  });
});
