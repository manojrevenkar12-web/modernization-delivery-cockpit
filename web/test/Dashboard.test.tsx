import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App, Dashboard } from "../src/app/App";
import type { DashboardData } from "../src/shared/data/types";
import raw from "../public/data.json";

const data = raw as unknown as DashboardData;
const ok = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
afterEach(cleanup);

describe("states", () => {
  it("shows a skeleton while loading", () => {
    render(<App fetcher={() => new Promise<Response>(() => {})} />);
    expect(screen.getByRole("status", { name: "Loading results" })).toBeTruthy();
  });
  it("explains a failure and retries", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: false, status: 500 } as Response).mockImplementationOnce(() => ok(data));
    render(<App fetcher={fetcher as unknown as typeof fetch} />);
    expect((await screen.findByRole("alert")).textContent).toContain("500");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeTruthy());
  });
  it("names the command for each empty section", () => {
    const empty: DashboardData = { cockpit: null, intake: null, parity_heldout: null, mistakes: null, eng_heldout: null, tests: null };
    render(<Dashboard data={empty} />);
    expect(screen.getByText(/parity --set heldout/)).toBeTruthy();
    expect(screen.getByText(/engagements --set heldout/)).toBeTruthy();
  });
});

describe("content", () => {
  it("states the committed date and status from the data", () => {
    render(<Dashboard data={data} />);
    expect(screen.getAllByText(new RegExp(String(data.cockpit!.facts.commit_date))).length).toBeGreaterThan(0);
  });
  it("opens a finding to show its evidence", () => {
    render(<Dashboard data={data} />);
    const f = screen.getByRole("button", { name: /F03/ });
    fireEvent.click(f);
    expect(f.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Evidence")).toBeTruthy();
  });
});
