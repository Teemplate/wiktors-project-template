import { vi } from "vitest";

/** Stub fetch with a handler; return an Error from it to simulate a failure. */
export function mockFetch(handler: (url: string) => unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = handler(String(url));
      if (body instanceof Error) throw body;
      return { ok: true, status: 200, json: async () => body } as Response;
    }),
  );
}
