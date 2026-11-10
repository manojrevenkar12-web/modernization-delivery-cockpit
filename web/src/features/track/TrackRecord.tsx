import type { MethodScore } from "../../shared/data/types";
import { pct } from "../../shared/format/format";
import { color, font, radius, size, space, stroke, weight } from "../../shared/theme/tokens";

const ROWS = [
  { key: "plan", label: "Single-number plan" },
  { key: "monte_carlo", label: "Team's own Monte Carlo, 85%" },
  { key: "reference_class", label: "Reference class, 85% (this cockpit)" },
] as const;
const TARGET = 0.85;

export function TrackRecord({ methods, engagements }: { methods: Record<string, MethodScore>; engagements: number }) {
  return (
    <div>
      {ROWS.map(({ key, label }) => {
        const s = methods[key];
        const mine = key === "reference_class";
        return (
          <div key={key} style={{ display: "grid", gridTemplateColumns: "minmax(200px, 1fr) 2fr", gap: space.md,
                                  alignItems: "center", padding: `${space.sm}px 0`,
                                  borderBottom: `${stroke.hair}px solid ${color.rule}` }}>
            <span style={{ fontWeight: mine ? weight.semibold : weight.regular }}>{label}
              <span style={{ display: "block", fontSize: size.small, color: color.graphite }}>
                {s.late_warned_before_due} of {s.late} late ones warned before the due date
              </span></span>
            <span style={{ position: "relative", display: "flex", alignItems: "center", gap: space.sm }}>
              <span style={{ position: "relative", flex: 1, height: stroke.bar, background: color.grid, borderRadius: radius.panel }}>
                <span style={{ position: "absolute", inset: 0, width: `${s.on_time * 100}%`,
                               background: mine ? color.accent : color.graphite, borderRadius: radius.panel }} />
                <span aria-hidden style={{ position: "absolute", left: `${TARGET * 100}%`, top: -space.xs, bottom: -space.xs,
                                           width: stroke.mark, background: color.ink }} />
              </span>
              <span style={{ fontFamily: font.figures, fontVariantNumeric: "tabular-nums", minWidth: space.xl + space.md }}>
                {pct(s.on_time)}
              </span>
            </span>
          </div>
        );
      })}
      <p style={{ color: color.graphite, fontSize: size.small }}>
        Share of {engagements} held-out simulated engagements finished by the date committed at kickoff. The black tick is 85%.
      </p>
    </div>
  );
}
