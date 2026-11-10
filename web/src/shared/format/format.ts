import type { Colour } from "../data/types";
import { color } from "../theme/tokens";

export const pct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x * 1000) / 10}%`);
export const ragColour = (c: Colour) => ({ green: color.green, amber: color.amber, red: color.red })[c];
export const ragLabel = (c: Colour) => ({ green: "On track", amber: "Needs a decision", red: "At risk" })[c];
export const longDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
