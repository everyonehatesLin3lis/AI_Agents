// Plain-language names for values the API returns as identifiers.

import type { Category, Severity } from "./types";

export const SERVICE_NAMES: Record<string, string> = {
  cloud_run: "Cloud Run",
  compute: "Compute Engine",
  cloud_sql: "Cloud SQL",
  cloud_storage: "Cloud Storage",
  gke: "GKE",
};

export function serviceName(id: string): string {
  return SERVICE_NAMES[id] ?? id;
}

// What each step of a review did, in the past tense: a step is shown once it has finished.
const STEP_LABELS: Record<string, string> = {
  parse: "Read the Terraform file",
  security_check: "Checked the security rules",
  cost_estimate: "Estimated the monthly cost",
  plan_research: "Decided what to look up in the documentation",
  retrieve: "Searched the Google Cloud documentation",
  grade_docs: "Kept the passages that are useful",
  rewrite_query: "Reworded the search and tried again",
  write_report: "Wrote the report",
};

export function stepLabel(id: string): string {
  return STEP_LABELS[id] ?? id;
}

export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const CATEGORY_LABELS: Record<Category, string> = {
  security: "Security",
  cost: "Cost",
  sizing: "Sizing",
  simplification: "Simpler setup",
};

export const REGIONS = [
  "us-central1",
  "us-east1",
  "us-west1",
  "europe-west1",
  "europe-west3",
  "europe-west4",
  "europe-north1",
  "asia-southeast1",
];

export function usd(amount: number, digits = 2): string {
  return `$${amount.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}
