import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewApp } from "./ReviewApp";
import { REPORT } from "@/lib/fixtures";
import type { Capabilities, ReviewEvent } from "@/lib/types";

const CAPABILITIES: Capabilities = {
  services: ["cloud_run", "compute", "cloud_sql", "cloud_storage", "gke"],
  resource_types: [],
  rule_count: 20,
  max_input_kb: 200,
  llm_configured: true,
  model: "google/gemini-3.5-flash-lite",
};
const SAMPLE = 'resource "google_compute_instance" "app" {}';

type Call = { url: string; method: string; body: unknown };

/** Fake the Python API at the network boundary and record what the screen sent. */
function fakeApi(reviewEvents: ReviewEvent[]) {
  const calls: Call[] = [];
  const json = (data: unknown) => new Response(JSON.stringify(data), { status: 200 });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url === "/api/capabilities") return json(CAPABILITIES);
      if (url === "/api/samples") return json({ samples: ["mixed/web_stack.tf"] });
      if (url === "/api/samples/mixed/web_stack.tf") return json({ terraform: SAMPLE });
      if (url.endsWith("/memory")) {
        return json(
          method === "PUT"
            ? JSON.parse(String(init?.body))
            : { budget_monthly_usd: null, region: null, preferences: [] },
        );
      }
      if (url === "/api/reviews") {
        return new Response(reviewEvents.map((e) => JSON.stringify(e)).join("\n") + "\n");
      }
      if (url.endsWith("/feedback")) return json({ status: "ok", saved: 1, ignored: 0 });
      return new Response("not found", { status: 404 });
    }),
  );
  return calls;
}

const FINISHED_REVIEW: ReviewEvent[] = [
  { type: "step", step: "parse" },
  { type: "step", step: "security_check" },
  { type: "step", step: "write_report" },
  { type: "report", report: REPORT, waiting_for_feedback: true },
];

afterEach(() => vi.unstubAllGlobals());

describe("ReviewApp", () => {
  it("explains itself, reviews a sample, shows progress and the report, and sends feedback", async () => {
    const calls = fakeApi(FINISHED_REVIEW);
    const user = userEvent.setup();
    render(<ReviewApp />);

    expect(await screen.findByRole("heading", { name: /what this tool does/i })).toBeVisible();

    await user.selectOptions(
      await screen.findByLabelText(/start from an example/i),
      "mixed/web_stack.tf",
    );
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Terraform" })).toHaveValue(SAMPLE));
    await user.click(screen.getByRole("button", { name: /^review$/i }));

    expect(await screen.findByText(REPORT.headline)).toBeVisible();
    expect(screen.getByText("Checked the security rules")).toBeVisible();
    expect(calls.find((c) => c.url === "/api/reviews")?.body).toEqual({
      terraform: SAMPLE,
      project_id: "default",
      options: {},
    });

    const feedback = screen.getByRole("region", { name: /your feedback/i });
    expect(within(feedback).queryByText(/open to the whole internet/i)).not.toBeInTheDocument();
    await user.click(within(feedback).getAllByLabelText(/not relevant/i)[0]);
    await user.click(within(feedback).getByRole("button", { name: /finish review/i }));

    expect(await screen.findByText(/feedback saved/i)).toBeVisible();
    expect(calls.find((c) => c.url === "/api/reviews/abc123/feedback")?.body).toEqual({
      feedback: [{ finding_index: 1, action: "dismiss", comment: "" }],
    });
  });

  it("shows why input was rejected instead of a report", async () => {
    fakeApi([{ type: "rejected", message: "The input does not look like Terraform." }]);
    const user = userEvent.setup();
    render(<ReviewApp />);

    await user.type(await screen.findByRole("textbox", { name: "Terraform" }), "hello");
    await user.click(screen.getByRole("button", { name: /^review$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/does not look like Terraform/);
    expect(screen.queryByRole("region", { name: /security findings/i })).not.toBeInTheDocument();
  });

  it("keeps advanced settings apart and sends only what was changed", async () => {
    const calls = fakeApi(FINISHED_REVIEW);
    const user = userEvent.setup();
    render(<ReviewApp />);

    const advanced = await screen.findByRole("group", { name: /advanced settings/i });
    await user.click(within(advanced).getByLabelText(/search the documentation/i));
    await user.type(screen.getByRole("textbox", { name: "Terraform" }), "resource x");
    await user.click(screen.getByRole("button", { name: /^review$/i }));

    await screen.findByText(REPORT.headline);
    expect(calls.find((c) => c.url === "/api/reviews")?.body).toMatchObject({
      options: { use_rag: false },
    });
  });

  it("saves the project's budget, region and preferences", async () => {
    const calls = fakeApi(FINISHED_REVIEW);
    const user = userEvent.setup();
    render(<ReviewApp />);

    const memory = await screen.findByRole("group", { name: /project memory/i });
    await user.type(within(memory).getByLabelText(/monthly budget/i), "100");
    await user.selectOptions(within(memory).getByLabelText(/default region/i), "europe-west1");
    await user.click(within(memory).getByRole("button", { name: /save/i }));

    expect(await within(memory).findByText(/saved/i)).toBeVisible();
    expect(calls.find((c) => c.method === "PUT")).toMatchObject({
      url: "/api/projects/default/memory",
      body: { budget_monthly_usd: 100, region: "europe-west1", preferences: [] },
    });
  });
});
