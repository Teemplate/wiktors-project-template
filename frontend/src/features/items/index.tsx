import { useEffect, useState } from "react";

import { API_BASE } from "../../lib/api";

/** Glue: web + api + postgres. The seeded rows, end to end. */
export type Item = { id: number; name: string; description: string };

export default function Items() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/items`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setItems)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <section>
      <h2>Items</h2>
      {/* Distinct states, because "empty" and "broken" are different problems
          and a spinner that never resolves hides both. The e2e suite asserts
          on the seeded rows, so an empty list is a failure there, not a pass. */}
      {error && <p data-testid="items-error">could not load items: {error}</p>}
      {!error && items === null && <p data-testid="items-loading">loading items…</p>}
      {!error && items?.length === 0 && (
        <p data-testid="items-empty">no items yet — run <code>python -m app.seed</code></p>
      )}
      {!!items?.length && (
        <ul data-testid="items-list">
          {items.map((item) => (
            <li key={item.id}>
              <strong>{item.name}</strong> — {item.description}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
