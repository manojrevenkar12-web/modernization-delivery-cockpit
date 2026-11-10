import type { DashboardData } from "../../shared/data/types";
import { color, font, size, space, stroke, weight } from "../../shared/theme/tokens";

const NAMES: Record<string, string> = {
  "dropped-inner-join": "Dropped an inner join",
  "forgot-lower-name": "Forgot lower(name) in search",
  "literal-underscore": "Read LIKE's _ literally",
  "unsorted-history": "Lost ORDER BY ORDERDATE",
  "inventory-increment": "Added stock instead of subtracting",
  "statusless-orders": "Shows orders without a status",
};

export function ParityPanel({ parity, mistakes }: { parity: NonNullable<DashboardData["parity_heldout"]>; mistakes: DashboardData["mistakes"] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: space.xl }}>
      <div>
        <div style={{ fontFamily: font.display, fontSize: size.figure, fontWeight: weight.semibold }}>
          {parity.agreed.toLocaleString("en-GB")} / {parity.operations.toLocaleString("en-GB")}
        </div>
        <p style={{ margin: 0, color: color.graphite }}>
          service calls answered identically by the legacy SQL and by MongoDB on the held-out workload;
          {" "}{parity.statements_validated} of {parity.statements_total} legacy statements validated.
        </p>
      </div>
      {mistakes && (
        <table style={{ width: "100%" }}>
          <caption style={{ textAlign: "left", fontWeight: weight.semibold, paddingBottom: space.sm }}>
            Mistakes planted in the MongoDB code
          </caption>
          <tbody>
            {Object.entries(mistakes).map(([k, v]) => (
              <tr key={k} style={{ borderBottom: `${stroke.hair}px solid ${color.rule}` }}>
                <td style={{ padding: `${space.xs}px 0` }}>{NAMES[k] ?? k}</td>
                <td style={{ textAlign: "right", color: v.caught ? color.green : color.red, fontWeight: weight.medium }}>
                  {v.caught ? "caught" : "missed"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
