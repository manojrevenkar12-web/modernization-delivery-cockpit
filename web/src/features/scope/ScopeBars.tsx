import { useState } from "react";
import type { WorkPackage } from "../../shared/data/types";
import { color, font, radius, size, space, stroke, weight } from "../../shared/theme/tokens";

export function ScopeBars({ wps }: { wps: WorkPackage[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const max = Math.max(...wps.map((w) => w.points));
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {wps.map((w) => {
        const isOpen = open === w.id;
        return (
          <li key={w.id} style={{ borderBottom: `${stroke.hair}px solid ${color.rule}` }}>
            <button type="button" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : w.id)}
              style={{ font: "inherit", width: "100%", textAlign: "left", background: "none", border: "none",
                       color: color.ink, cursor: "pointer", padding: `${space.sm}px 0`, display: "grid",
                       gridTemplateColumns: "minmax(180px, 1.2fr) 2fr", gap: space.md, alignItems: "center" }}>
              <span><span style={{ fontWeight: weight.semibold }}>{w.name}</span>
                <span style={{ display: "block", fontSize: size.small, color: color.graphite }}>
                  {w.drivers.statements} statements, {w.drivers.writes} writes, {w.findings.length} findings
                </span></span>
              <span style={{ display: "flex", alignItems: "center", gap: space.sm }}>
                <span style={{ height: stroke.bar, width: `${(w.points / max) * 100}%`, background: color.accent,
                               borderRadius: radius.panel }} />
                <span style={{ fontFamily: font.figures, fontVariantNumeric: "tabular-nums" }}>{w.points}</span>
              </span>
            </button>
            {isOpen && (
              <p style={{ margin: `0 0 ${space.md}px`, color: color.graphite, fontSize: size.small }}>
                {w.statements.length ? `Legacy statements: ${w.statements.join(", ")}.` : "No legacy statements: data and cut-over work."}
                {w.findings.length ? ` Findings: ${w.findings.join(", ")}.` : ""}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
