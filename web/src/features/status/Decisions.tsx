import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import type { Decision, Finding } from "../../shared/data/types";
import { color, motion as m, size, space, stroke, weight } from "../../shared/theme/tokens";

const SEVERITY = { high: color.red, medium: color.amber, low: color.graphite } as const;

export function Decisions({ findings, decisions }: { findings: Finding[]; decisions: Decision[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const byFinding = Object.fromEntries(decisions.map((d) => [d.finding, d]));
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {findings.map((f) => {
        const d = byFinding[f.id];
        const isOpen = open === f.id;
        return (
          <li key={f.id} style={{ borderBottom: `${stroke.hair}px solid ${color.rule}` }}>
            <button type="button" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : f.id)}
              style={{ font: "inherit", width: "100%", textAlign: "left", background: "none", border: "none", color: color.ink,
                       cursor: "pointer", padding: `${space.md}px 0`, display: "flex", justifyContent: "space-between",
                       gap: space.md, flexWrap: "wrap" }}>
              <span><span style={{ color: SEVERITY[f.severity], fontWeight: weight.semibold }}>{f.id} {f.severity}</span>{" "}
                {f.title}</span>
              <span style={{ color: d ? color.green : color.amber, fontWeight: weight.medium }}>
                {d ? `Decided ${d.date}` : "Decision needed"}
              </span>
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }} transition={{ duration: m.quickSeconds, ease: m.ease }}
                            style={{ overflow: "hidden" }}>
                  <dl style={{ margin: `0 0 ${space.md}px`, fontSize: size.small, color: color.graphite }}>
                    <dt style={{ fontWeight: weight.semibold, color: color.ink }}>Evidence</dt><dd style={{ margin: 0 }}>{f.evidence}</dd>
                    <dt style={{ fontWeight: weight.semibold, color: color.ink, marginTop: space.sm }}>
                      {d ? `Decision (${d.owner})` : "Proposed action"}</dt>
                    <dd style={{ margin: 0 }}>{d ? d.decision : f.action}</dd>
                  </dl>
                </motion.div>
              )}
            </AnimatePresence>
          </li>
        );
      })}
    </ul>
  );
}
