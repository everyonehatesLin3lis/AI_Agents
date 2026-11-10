import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Progress } from "./Progress";

describe("Progress", () => {
  it("shows each finished step in plain words and that work is still going on", () => {
    render(<Progress steps={["parse", "security_check"]} running />);

    expect(screen.getByText("Read the Terraform file")).toBeInTheDocument();
    expect(screen.getByText("Checked the security rules")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/working/i);
  });

  it("stops saying it is working when the review is done", () => {
    render(<Progress steps={["parse", "write_report"]} running={false} />);

    expect(screen.getByText("Wrote the report")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
