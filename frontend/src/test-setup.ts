// jsdom does not implement fetch; every component here uses it. Tests stub it
// per-case, but this guarantees a clear failure rather than "fetch is not
// defined" if one forgets.
if (typeof globalThis.fetch === "undefined") {
  globalThis.fetch = (() => {
    throw new Error("fetch was called but not stubbed in this test");
  }) as unknown as typeof fetch;
}
