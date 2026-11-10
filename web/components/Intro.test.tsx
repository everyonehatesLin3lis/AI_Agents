import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Intro } from "./Intro";
import type { Capabilities } from "@/lib/types";

const capabilities: Capabilities = {
  services: ["cloud_run", "compute", "cloud_sql", "cloud_storage", "gke"],
  resource_types: ["google_storage_bucket"],
  rule_count: 20,
  max_input_kb: 200,
  llm_configured: true,
  model: "google/gemini-3.5-flash-lite",
};

describe("Intro", () => {
  it("tells the user what the tool does and what it never does", () => {
    render(<Intro capabilities={capabilities} />);

    expect(screen.getByRole("heading", { name: /what this tool does/i })).toBeInTheDocument();
    expect(screen.getByText(/20 fixed security rules/i)).toBeInTheDocument();
    expect(screen.getByText(/monthly cost/i)).toBeInTheDocument();
    expect(screen.getByText(/never creates, changes or deletes anything/i)).toBeInTheDocument();
  });

  it("names the five supported services in plain words", () => {
    render(<Intro capabilities={capabilities} />);

    for (const name of ["Cloud Run", "Compute Engine", "Cloud SQL", "Cloud Storage", "GKE"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
  });

  it("lists what the tool does not do, including the size limit from the API", () => {
    render(<Intro capabilities={capabilities} />);

    expect(screen.getByText(/what it does not do/i)).toBeInTheDocument();
    expect(screen.getByText(/other google cloud services/i)).toBeInTheDocument();
    expect(screen.getByText(/variables, modules/i)).toBeInTheDocument();
    expect(screen.getByText(/200 KB/)).toBeInTheDocument();
  });

  it("says so when AI suggestions are unavailable", () => {
    render(<Intro capabilities={{ ...capabilities, llm_configured: false }} />);

    expect(screen.getByText(/no AI model is configured/i)).toBeInTheDocument();
  });
});
