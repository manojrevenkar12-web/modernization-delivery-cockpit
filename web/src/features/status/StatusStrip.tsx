import type { Cockpit } from "../../shared/data/types";
import { ragColour, ragLabel } from "../../shared/format/format";
import { color, font, size, space, stroke, weight } from "../../shared/theme/tokens";

export function StatusStrip({ status }: { status: Cockpit["status"] }) {
  const areas = ["schedule", "quality", "risk"] as const;
  return (
    <div role="list" aria-label="Status by area"
         style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: space.lg,
                  borderTop: `${stroke.hair}px solid ${color.rule}`, paddingTop: space.lg }}>
      {areas.map((a) => (
        <div role="listitem" key={a}>
          <div style={{ display: "flex", alignItems: "center", gap: space.sm, fontWeight: weight.semibold }}>
            <span aria-hidden style={{ width: space.md / 2 + space.xs, height: space.md / 2 + space.xs, borderRadius: "50%",
                                       background: ragColour(status[a].colour) }} />
            <span style={{ fontFamily: font.display }}>{a[0].toUpperCase() + a.slice(1)}</span>
            <span style={{ color: ragColour(status[a].colour), fontSize: size.small }}>{ragLabel(status[a].colour)}</span>
          </div>
          <p style={{ margin: `${space.xs}px 0 0`, color: color.graphite }}>{status[a].reason}</p>
        </div>
      ))}
    </div>
  );
}
