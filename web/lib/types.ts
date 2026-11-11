// The JSON the Python API returns. These mirror the Pydantic models in the Python
// project (agent/service.py, agent/state.py, tools/models.py, memory/store.py).

export type Capabilities = {
  services: string[];
  resource_types: string[];
  rule_count: number;
  max_input_kb: number;
  llm_configured: boolean;
  model: string;
};

export type Severity = "critical" | "high" | "medium" | "low";
export type Category = "security" | "cost" | "sizing" | "simplification";

export type Finding = {
  severity: Severity;
  resource: string;
  issue: string;
  recommendation: string;
  estimated_savings: number | null;
  source_url: string | null;
  rule_id: string | null;
  category: Category;
  deprioritized: boolean;
  // For a rule finding: what the file says in the attributes the rule read.
  terraform_fields: string[];
};

export type CostLine = {
  resource: string;
  service: string;
  monthly_usd: number;
  priced: boolean;
  assumptions: string[];
};

export type CostEstimate = {
  lines: CostLine[];
  total_monthly_usd: number;
  currency: string;
  default_region: string;
  regions_used: string[];
  price_source: string;
  prices_may_be_outdated: boolean;
  notes: string[];
};

export type Usage = {
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  calls_by_node: Record<string, number>;
};

export type ReviewReport = {
  review_id: string;
  project_id: string;
  status: "ok" | "failed";
  model: string;
  headline: string;
  summary: string;
  findings: Finding[];
  cost_estimate: CostEstimate | null;
  resources_reviewed: number;
  unsupported_resources: string[];
  warnings: string[];
  sources: string[];
  usage: Usage;
  timings: Record<string, number>;
};

export type ReviewEvent = {
  type: "step" | "report" | "rejected" | "error";
  step?: string;
  report?: ReviewReport;
  waiting_for_feedback?: boolean;
  message?: string;
};

export type ReviewOptions = {
  model?: string;
  temperature?: number;
  use_rag?: boolean;
  max_rewrites?: number;
  extra_instructions?: string;
};

export type ReviewRequest = {
  terraform: string;
  project_id: string;
  options?: ReviewOptions;
};

export type ProjectMemory = {
  budget_monthly_usd: number | null;
  region: string | null;
  preferences: string[];
};

export type FeedbackAction = "helpful" | "dismiss";

export type FeedbackChoice = {
  finding_index: number;
  action: FeedbackAction;
  comment?: string;
};

export type FinishResult = {
  status: "ok" | "not_found" | "already_finished";
  saved: number;
  ignored: number;
};
