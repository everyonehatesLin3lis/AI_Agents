import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Report } from "./Report";
import { REPORT } from "@/lib/fixtures";

describe("Report", () => {
  it("shows the headline and says where the security findings come from", () => {
    render(<Report report={REPORT} />);

    expect(screen.getByText(REPORT.headline)).toBeInTheDocument();
    const security = screen.getByRole("region", { name: /security findings/i });
    expect(within(security).getByText(/fixed rules/i)).toBeInTheDocument();
    expect(within(security).getByText("Critical")).toBeInTheDocument();
    expect(within(security).getByText("SQL-001")).toBeInTheDocument();
    expect(within(security).getByText("google_sql_database_instance.db")).toBeInTheDocument();
  });

  it("marks suggestions as AI-written, links their source, and flags the ones without one", () => {
    render(<Report report={REPORT} />);

    const suggestions = screen.getByRole("region", { name: /suggestions/i });
    expect(within(suggestions).getByText(/written by an AI model/i)).toBeInTheDocument();
    expect(within(suggestions).getByRole("link", { name: /what-is-cloud-run/i })).toHaveAttribute(
      "href",
      "https://cloud.google.com/run/docs/overview/what-is-cloud-run",
    );
    expect(within(suggestions).getByText(/no documentation source/i)).toBeInTheDocument();
    expect(within(suggestions).getByText(/lower priority/i)).toBeInTheDocument();
    expect(within(suggestions).getByText(/\$40\.00 per month/)).toBeInTheDocument();
  });

  it("shows the cost per resource with its assumptions and the total", () => {
    render(<Report report={REPORT} />);

    const cost = screen.getByRole("region", { name: /cost estimate/i });
    expect(within(cost).getByText(/\$124\.32 per month/)).toBeInTheDocument();
    expect(within(cost).getByText("$113.62")).toBeInTheDocument();
    expect(within(cost).getByText(/count = 2\./)).toBeInTheDocument();
    expect(within(cost).getByText(/prices may be outdated/i)).toBeInTheDocument();
  });

  it("lists what was not reviewed and what the review itself cost", () => {
    render(<Report report={REPORT} />);

    expect(screen.getByText("google_pubsub_topic.events")).toBeInTheDocument();
    expect(screen.getByText(/4,413 in, 311 out/)).toBeInTheDocument();
    expect(screen.getByText(/\$0\.0021/)).toBeInTheDocument();
    expect(screen.getByText(/14\.6 seconds/)).toBeInTheDocument();
  });
});

describe("Report with incomplete data", () => {
  it("still renders when the API leaves an optional value out", () => {
    const finding = { ...REPORT.findings[1] } as Record<string, unknown>;
    delete finding.estimated_savings;
    delete finding.source_url;
    const report = {
      ...REPORT,
      findings: [finding],
      usage: { ...REPORT.usage, cost_usd: undefined },
    } as unknown as typeof REPORT;

    render(<Report report={report} />);

    expect(screen.getByText(/consider cloud run/i)).toBeInTheDocument();
    expect(screen.queryByText(/possible saving/i)).not.toBeInTheDocument();
    expect(screen.getByText(/unknown for this model/i)).toBeInTheDocument();
  });
});

describe("Report with a budget finding", () => {
  it("shows a finding made by code in the cost section, not as AI-written advice", () => {
    const budget = {
      severity: "medium" as const,
      resource: "(whole configuration)",
      issue: "Estimated cost $124.32/month is $24.32 above the project budget of $100.00.",
      recommendation: "Start with the largest line: google_compute_instance.app ($113.62/month).",
      estimated_savings: null,
      source_url: null,
      rule_id: "COST-BUDGET",
      category: "cost" as const,
      deprioritized: false,
    };
    render(<Report report={{ ...REPORT, findings: [...REPORT.findings, budget] }} />);

    const cost = screen.getByRole("region", { name: /cost estimate/i });
    const suggestions = screen.getByRole("region", { name: /suggestions/i });
    expect(within(cost).getByText(/above the project budget/i)).toBeInTheDocument();
    expect(within(cost).getByText(/from the budget you saved/i)).toBeInTheDocument();
    expect(within(suggestions).queryByText(/above the project budget/i)).not.toBeInTheDocument();
  });
});

describe("Report field trace", () => {
  it("shows which Terraform field triggered a rule finding, and nothing for AI suggestions", () => {
    render(<Report report={REPORT} />);

    const security = screen.getByRole("region", { name: /security findings/i });
    const suggestions = screen.getByRole("region", { name: /suggestions/i });
    expect(within(security).getByText(/in your terraform/i)).toBeInTheDocument();
    expect(
      within(security).getByText('settings.ip_configuration.authorized_networks.value = "0.0.0.0/0"'),
    ).toBeInTheDocument();
    expect(within(suggestions).queryByText(/in your terraform/i)).not.toBeInTheDocument();
  });
});
