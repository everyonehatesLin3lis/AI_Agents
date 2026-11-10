import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FeedbackForm } from "./FeedbackForm";
import { REPORT } from "@/lib/fixtures";

const BUDGET = {
  severity: "medium" as const,
  resource: "(whole configuration)",
  issue: "Estimated cost is above the project budget.",
  recommendation: "Start with the largest line.",
  estimated_savings: null,
  source_url: null,
  rule_id: "COST-BUDGET",
  category: "cost" as const,
  deprioritized: false,
};

describe("FeedbackForm", () => {
  it("offers only AI suggestions: not security findings, not the budget check", () => {
    render(
      <FeedbackForm report={{ ...REPORT, findings: [...REPORT.findings, BUDGET] }} onSubmit={vi.fn()} />,
    );

    expect(screen.getAllByRole("group")).toHaveLength(2);
    expect(screen.queryByText(/open to the whole internet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/above the project budget/i)).not.toBeInTheDocument();
  });

  it("sends each answer with the finding's position in the report and its comment", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<FeedbackForm report={REPORT} onSubmit={onSubmit} />);

    await user.click(screen.getAllByLabelText("Helpful")[0]);
    await user.type(screen.getAllByLabelText(/comment/i)[0], "good idea");
    await user.click(screen.getAllByLabelText(/not relevant/i)[1]);
    await user.click(screen.getByRole("button", { name: /finish review/i }));

    expect(onSubmit).toHaveBeenCalledWith([
      { finding_index: 1, action: "helpful", comment: "good idea" },
      { finding_index: 2, action: "dismiss", comment: "" },
    ]);
  });
});
