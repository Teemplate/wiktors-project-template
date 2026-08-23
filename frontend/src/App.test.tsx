/**
 * Unit tests: fast, no browser, no backend.
 *
 * These cover the states that are awkward to reach end-to-end -- an API error,
 * an empty list -- while `e2e/smoke.spec.ts` covers the real path against a
 * real seeded stack. Between them, "loading forever" cannot pass unnoticed.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(handler: (url: string) => unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = handler(String(url));
      if (body instanceof Error) throw body;
      return { ok: true, status: 200, json: async () => body } as Response;
    }),
  );
}

describe("App", () => {
  it("renders the seeded items", async () => {
    mockFetch((url) =>
      url.includes("/api/items")
        ? [{ id: 1, name: "First item", description: "desc" }]
        : { message: "hello from test" },
    );

    render(<App />);
    await waitFor(() => expect(screen.getByTestId("items-list")).toBeTruthy());
    expect(screen.getByText("First item")).toBeTruthy();
  });

  it("says so when there are no items, rather than spinning", async () => {
    mockFetch((url) => (url.includes("/api/items") ? [] : { message: "hi" }));

    render(<App />);
    await waitFor(() => expect(screen.getByTestId("items-empty")).toBeTruthy());
  });

  it("distinguishes a broken API from an empty one", async () => {
    mockFetch((url) =>
      url.includes("/api/items") ? new Error("boom") : { message: "hi" },
    );

    render(<App />);
    await waitFor(() => expect(screen.getByTestId("items-error")).toBeTruthy());
  });
});
