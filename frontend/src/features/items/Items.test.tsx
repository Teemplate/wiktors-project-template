/**
 * These cover the states that are awkward to reach end-to-end -- an API error,
 * an empty list -- while `e2e/items.spec.ts` covers the real path against a
 * real seeded stack. Between them, "loading forever" cannot pass unnoticed.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockFetch } from "../../test-utils";
import Items from ".";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Items", () => {
  it("renders the seeded items", async () => {
    mockFetch(() => [{ id: 1, name: "First item", description: "desc" }]);
    render(<Items />);
    await waitFor(() => expect(screen.getByTestId("items-list")).toBeTruthy());
    expect(screen.getByText("First item")).toBeTruthy();
  });

  it("says so when there are no items, rather than spinning", async () => {
    mockFetch(() => []);
    render(<Items />);
    await waitFor(() => expect(screen.getByTestId("items-empty")).toBeTruthy());
  });

  it("distinguishes a broken API from an empty one", async () => {
    mockFetch(() => new Error("boom"));
    render(<Items />);
    await waitFor(() => expect(screen.getByTestId("items-error")).toBeTruthy());
  });
});
