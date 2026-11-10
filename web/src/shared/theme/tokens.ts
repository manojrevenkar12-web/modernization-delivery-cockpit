// Design tokens: every colour, size, space and duration the dashboard uses.
// A steering-committee pack: quiet paper, dark ink, one teal for this cockpit's
// own numbers, and accessible red/amber/green reserved for status.

export const color = {
  paper: "#F5F6F4",
  sheet: "#FFFFFF",
  ink: "#1C2421",
  graphite: "#5B6661",
  rule: "#D5DAD6",
  grid: "#E6EAE7",
  accent: "#1F5C57",
  spread: "#A9C2BE",
  green: "#2D7A4B",
  amber: "#9A5B00",
  red: "#B3261E",
  focus: "#2457C5",
  // Kept for the shared components copied from the house kit.
  canH: "#1F5C57",
  canL: "#2D7A4B",
  hv: "#B3261E",
  shield: "#5B6661",
} as const;

export const font = {
  body: "'Public Sans', system-ui, sans-serif",
  display: "'Literata', Georgia, serif",
  figures: "'Public Sans', system-ui, sans-serif",
} as const;

export const size = {
  small: "0.8125rem",
  body: "1rem",
  lead: "1.25rem",
  h2: "1.75rem",
  h1: "2.75rem",
  figure: "2.25rem",
} as const;

export const weight = { regular: 400, medium: 500, semibold: 600 } as const;
export const leading = { tight: 1.12, body: 1.55 } as const;
export const space = { xs: 4, sm: 8, md: 16, lg: 24, xl: 40, xxl: 80 } as const;
export const radius = { control: 6, panel: 4 } as const;
export const measure = { page: 1060, text: 660 } as const;
export const stroke = { hair: 1, mark: 2, bar: 14 } as const;
export const motion = { growSeconds: 0.9, staggerSeconds: 0.012, quickSeconds: 0.22, ease: [0.22, 1, 0.36, 1] as const } as const;
export const chart = { width: 1000, height: 320, padLeft: 8, padBottom: 56, padTop: 92, label: 13, tick: 12, labelRow: 36, labelGap: 6, flipAt: 0.78 } as const;
export const meter = { tick: 6, height: 14, gap: 2 } as const;
