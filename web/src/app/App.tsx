import { ForecastChart } from "../features/forecast/ForecastChart";
import { ParityPanel } from "../features/parity/ParityPanel";
import { ScopeBars } from "../features/scope/ScopeBars";
import { Decisions } from "../features/status/Decisions";
import { StatusStrip } from "../features/status/StatusStrip";
import { TrackRecord } from "../features/track/TrackRecord";
import type { DashboardData } from "../shared/data/types";
import { useDashboard } from "../shared/data/useDashboard";
import { ragColour } from "../shared/format/format";
import { color, font, leading, measure, size, space, weight } from "../shared/theme/tokens";
import { Button } from "../shared/ui/Button";
import { Command, Notice } from "../shared/ui/Notice";
import { Section } from "../shared/ui/Section";
import { PageSkeleton } from "../shared/ui/Skeleton";

const REPO = "https://github.com/manojrevenkar12-web/modernization-delivery-cockpit";

function Missing({ command, what }: { command: string; what: string }) {
  return <Notice tone="empty">No {what} yet. Run <Command>{command}</Command>, then <Command>python -m mdc report</Command>.</Notice>;
}

export function Dashboard({ data }: { data: DashboardData }) {
  const c = data.cockpit;
  return (
    <>
      <header style={{ marginBottom: space.xl }}>
        <p style={{ margin: 0, color: color.graphite }}>JPetStore 6, legacy Java and SQL, moving to MongoDB</p>
        <h1 style={{ fontFamily: font.display, fontSize: size.h1, lineHeight: leading.tight, fontWeight: weight.semibold,
                     margin: `${space.sm}px 0 ${space.md}px`, maxWidth: measure.text }}>
          When will it be done, and how sure are we?
        </h1>
        {c && (
          <p style={{ fontSize: size.lead, maxWidth: measure.text, margin: 0 }}>
            Status for the week ending {c.facts.status_week}:{" "}
            <strong style={{ color: ragColour(c.status.overall) }}>{c.status.overall}</strong>. Committed finish{" "}
            {c.facts.commit_date}, against a customer target of {c.facts.target_date}.
          </p>
        )}
      </header>
      {c ? (<><ForecastChart cockpit={c} /><div style={{ marginTop: space.xl }}><StatusStrip status={c.status} /></div></>)
         : <Missing command="python -m mdc cockpit" what="forecast" />}

      <Section id="scope" title="Scope read from the code"
        intro={data.intake ? `Work packages come from the legacy app itself: ${data.intake.inventory.statements} SQL statements in ${data.intake.inventory.tables} tables, grouped by the capability they serve and sized by their writes, joins and findings. Open one to see its statements.` : undefined}>
        {c ? <ScopeBars wps={c.work_packages} /> : <Missing command="python -m mdc intake" what="analysis" />}
      </Section>

      <Section id="parity" title="Proof it behaves the same"
        intro="The same user journeys run against the original SQL and the MongoDB version; every answer is compared. Planted translation mistakes show whether the comparison would notice.">
        {data.parity_heldout ? <ParityPanel parity={data.parity_heldout} mistakes={data.mistakes} />
          : <Missing command="python -m mdc parity --set heldout" what="held-out parity run" />}
      </Section>

      <Section id="track" title="Does the commitment hold?"
        intro="Dates committed at kickoff, checked against engagements that ran to the end. Committing to what past engagements actually took is the only method that keeps its promise.">
        {data.eng_heldout ? <TrackRecord methods={data.eng_heldout.score.methods} engagements={data.eng_heldout.score.engagements} />
          : <Missing command="python -m mdc engagements --set heldout" what="forecasting track record" />}
      </Section>

      <Section id="decisions" title="Decisions and open risks"
        intro="Every finding comes from a rule over the code and carries its evidence. A high finding without a decision turns the risk status amber.">
        {c ? (c.findings.length ? <Decisions findings={c.findings} decisions={c.decisions} />
              : <Notice tone="empty">The analysis raised no findings.</Notice>)
           : <Missing command="python -m mdc cockpit" what="findings" />}
      </Section>

      <footer style={{ marginTop: space.xxl, color: color.graphite, fontSize: size.small }}>
        <a href={REPO}>Source on GitHub</a>
        {data.tests && <span style={{ marginLeft: space.lg }}>{data.tests.passed} tests passing</span>}
        <span style={{ marginLeft: space.lg }}>Every number here is generated from reports/*.json.</span>
      </footer>
    </>
  );
}

export function App({ fetcher }: { fetcher?: typeof fetch } = {}) {
  const { state, retry } = useDashboard(fetcher);
  return (
    <main style={{ maxWidth: measure.page, margin: "0 auto", padding: `${space.xl}px ${space.lg}px` }}>
      {state.status === "loading" && <PageSkeleton />}
      {state.status === "error" && (
        <Notice tone="error" action={<Button onClick={retry}>Try again</Button>}>
          The results could not be loaded ({state.message}). Generate them with <Command>python -m mdc report</Command>.
        </Notice>
      )}
      {state.status === "ready" && <Dashboard data={state.data} />}
    </main>
  );
}
