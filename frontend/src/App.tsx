import type { ComponentType } from "react";

/**
 * The shell. Everything that talks to another block is a *feature* in
 * src/features/<name>/index.tsx, discovered here rather than imported by name:
 * a feature that needs the api block is removed by deleting its directory, and
 * nothing else has to change. See docs/BLOCKS.md.
 */
const modules = import.meta.glob<{ default: ComponentType }>("./features/*/index.tsx", {
  eager: true,
});

export const features = Object.keys(modules)
  .sort()
  .map((path) => ({ path, Feature: modules[path].default }));

export default function App() {
  return (
    <main style={{ fontFamily: "system-ui", padding: "3rem" }}>
      <h1>Project Template</h1>
      {features.map(({ path, Feature }) => (
        <Feature key={path} />
      ))}
    </main>
  );
}
