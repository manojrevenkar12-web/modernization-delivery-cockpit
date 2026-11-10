import { motion, useReducedMotion } from "framer-motion";
import type { Cockpit } from "../../shared/data/types";
import { longDate } from "../../shared/format/format";
import { chart, color, font, motion as m, stroke, weight } from "../../shared/theme/tokens";

// The signature view: how likely each finish is, with the dates a steering
// committee argues about marked on it.
export function ForecastChart({ cockpit }: { cockpit: Cockpit }) {
  const reduce = useReducedMotion();
  const f = cockpit.facts;
  const { step, bins } = cockpit.histogram;
  const marks = [
    { key: "plan", sprints: Number(f.plan_sprints), date: String(f.plan_date), label: "Plan", tone: color.graphite },
    { key: "p50", sprints: Number(f.mc_p50_sprints), date: String(f.p50_date), label: "50% likely", tone: color.ink },
    { key: "commit", sprints: Number(f.commit_sprints), date: String(f.commit_date), label: "Committed, 85%", tone: color.accent },
    { key: "target", sprints: Number(f.target_sprints), date: String(f.target_date), label: "Customer target", tone: color.amber },
  ];
  const maxX = Math.max(...marks.map((k) => k.sprints), ...bins.map(([b]) => b + step)) * 1.05;
  const maxY = Math.max(...bins.map(([, n]) => n));
  const plotH = chart.height - chart.padBottom - chart.padTop;
  const x = (s: number) => chart.padLeft + (s / maxX) * (chart.width - 2 * chart.padLeft);
  const barW = Math.max(1, x(step) - x(0) - 1);
  const sprintTicks = Array.from({ length: Math.floor(maxX) + 1 }, (_, i) => i);
  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${chart.width} ${chart.height}`} width="100%" role="img"
           aria-label={`Forecast of finishing: 50% likely ${f.p50_date}, committed ${f.commit_date}, target ${f.target_date}`}>
        {bins.map(([b, n], i) => {
          const h = (n / maxY) * plotH;
          return (
            <motion.rect key={b} x={x(b)} width={barW} fill={color.spread}
              initial={reduce ? false : { y: chart.height - chart.padBottom, height: 0 }}
              animate={{ y: chart.height - chart.padBottom - h, height: h }}
              transition={{ duration: m.growSeconds, delay: reduce ? 0 : i * m.staggerSeconds, ease: m.ease }} />
          );
        })}
        <line x1={chart.padLeft} x2={chart.width - chart.padLeft} y1={chart.height - chart.padBottom}
              y2={chart.height - chart.padBottom} stroke={color.rule} strokeWidth={stroke.hair} />
        {sprintTicks.map((t) => (
          <text key={t} x={x(t)} y={chart.height - chart.padBottom + chart.labelRow / 2} fontSize={chart.tick}
                fontFamily={font.body} fill={color.graphite} textAnchor={t === 0 ? "start" : "middle"}>
            {t === 0 ? "start" : `sprint ${t}`}</text>
        ))}
        {marks.map((k, i) => {
          const top = chart.padTop - chart.labelGap - (i % 2 ? 0 : chart.labelRow);
          const flip = x(k.sprints) > chart.width * chart.flipAt;
          const tx = x(k.sprints) + (flip ? -chart.labelGap : chart.labelGap);
          const anchor = flip ? "end" : "start";
          return (
            <motion.g key={k.key} initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }}
                      transition={{ delay: reduce ? 0 : m.growSeconds, duration: m.quickSeconds }}>
              <line x1={x(k.sprints)} x2={x(k.sprints)} y1={top - chart.label} y2={chart.height - chart.padBottom}
                    stroke={k.tone} strokeWidth={k.key === "commit" ? stroke.mark + 1 : stroke.mark}
                    strokeDasharray={k.key === "plan" ? "4 4" : undefined} />
              <text x={tx} y={top - chart.label} fontSize={chart.label} fontFamily={font.body} textAnchor={anchor}
                    fontWeight={weight.semibold} fill={k.tone}>{k.label}</text>
              <text x={tx} y={top + chart.labelGap} fontSize={chart.tick} fontFamily={font.body} textAnchor={anchor}
                    fill={color.graphite}>{longDate(k.date)}</text>
            </motion.g>
          );
        })}
      </svg>
      <figcaption style={{ color: color.graphite, fontSize: "0.8125rem" }}>
        Bars: how often each finish came up in the team's Monte Carlo forecast. The committed date is the plan
        stretched by what past engagements actually took.
      </figcaption>
    </figure>
  );
}
