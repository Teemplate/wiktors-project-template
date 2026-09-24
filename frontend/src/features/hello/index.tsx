import { useEffect, useState } from "react";

import { API_BASE } from "../../lib/api";

/** Glue: web + api. Proves the browser reaches the api, with no database. */
export default function Hello() {
  const [message, setMessage] = useState("loading…");

  useEffect(() => {
    fetch(`${API_BASE}/api/hello`)
      .then((r) => r.json())
      .then((d) => setMessage(d.message))
      .catch(() => setMessage("backend unreachable"));
  }, []);

  return <p data-testid="hello">{message}</p>;
}
