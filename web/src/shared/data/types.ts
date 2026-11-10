// Shapes of web/public/data.json, written by `python -m mdc report`.

export type Colour = "green" | "amber" | "red";

export interface Finding { id: string; kind: string; severity: "high" | "medium" | "low"; title: string; evidence: string; action: string }
export interface Decision { finding: string; decision: string; owner: string; date: string; status: string }
export interface WorkPackage { id: string; name: string; statements: string[]; drivers: Record<string, number>; findings: string[]; points: number }

export interface Cockpit {
  facts: Record<string, string | number>;
  status: { overall: Colour } & Record<"schedule" | "quality" | "risk", { colour: Colour; reason: string }>;
  histogram: { step: number; bins: [number, number][] };
  work_packages: WorkPackage[];
  findings: Finding[];
  decisions: Decision[];
}

export interface MethodScore {
  on_time: number; late: number; late_warned_before_due: number;
  median_warning_lead_sprints: number | null; false_alarms: number; median_buffer_sprints: number;
}

export interface DashboardData {
  cockpit: Cockpit | null;
  intake: { inventory: Record<string, number> } | null;
  parity_heldout: { operations: number; agreed: number; statements_total: number; statements_validated: number; backend: string } | null;
  mistakes: Record<string, { caught: boolean; doc: string; first_caught_at_call: number | null }> | null;
  eng_heldout: { score: { engagements: number; methods: Record<"plan" | "monte_carlo" | "reference_class", MethodScore> } } | null;
  tests: { total: number; passed: number; failed: number } | null;
}
