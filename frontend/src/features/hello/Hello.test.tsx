import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockFetch } from "../../test-utils";
import Hello from ".";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Hello", () => {
  it("shows the api's greeting", async () => {
    mockFetch(() => ({ message: "hello from test" }));
    render(<Hello />);
    await waitFor(() => expect(screen.getByText("hello from test")).toBeTruthy());
  });

  it("says so when the api is unreachable", async () => {
    mockFetch(() => new Error("down"));
    render(<Hello />);
    await waitFor(() => expect(screen.getByText("backend unreachable")).toBeTruthy());
  });
});
