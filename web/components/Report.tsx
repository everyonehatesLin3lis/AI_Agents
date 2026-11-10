import { CATEGORY_LABELS, SEVERITY_LABELS, serviceName, usd } from "@/lib/labels";
import type { CostEstimate, Finding, ReviewReport } from "@/lib/types";

const NO_SOURCE_PREFIX = "Suggestion (no documentation source): ";

function FindingCard({ finding }: { finding: Finding }) {
  const withoutSource = !finding.source_url && finding.category !== "security";
  const recommendation = finding.recommendation.startsWith(NO_SOURCE_PREFIX)
    ? finding.recommendation.slice(NO_SOURCE_PREFIX.length)
    : finding.recommendation;
  return (
    <li className={`finding severity-${finding.severity}`}>
      <p className="finding-head">
        <span className="badge">{SEVERITY_LABELS[finding.severity]}</span>
        <span className="rule">{finding.rule_id ?? CATEGORY_LABELS[finding.category]}</span>
        <code>{finding.resource}</code>
      </p>
      <p>
        <strong>Issue:</strong> {finding.issue}
      </p>
      <p>
        <strong>What to do:</strong> {recommendation}
      </p>
      {finding.estimated_savings != null && (
        <p>
          <strong>Possible saving:</strong> {usd(finding.estimated_savings)} per month
        </p>
      )}
      {finding.source_url && (
        <p>
          <strong>Source:</strong>{" "}
          <a href={finding.source_url} target="_blank" rel="noopener noreferrer">
            {finding.source_url}
          </a>
        </p>
      )}
      {withoutSource && (
        <p className="muted">No documentation source: read this as a suggestion, not a fact.</p>
      )}
      {finding.deprioritized && (
        <p className="muted">Lower priority because of your earlier feedback.</p>
      )}
    </li>
  );
}

function Cost({ cost }: { cost: CostEstimate | null }) {
  if (!cost) return <p>No cost estimate is available.</p>;
  return (
    <>
      <p className="total">
        Total: <strong>{usd(cost.total_monthly_usd)} per month</strong>
      </p>
      <p className="muted">
        A list-price estimate, priced in {cost.regions_used.join(", ") || cost.default_region}.
        Traffic, data transfer and discounts are not included.
      </p>
      <table>
        <thead>
          <tr>
            <th scope="col">Resource</th>
            <th scope="col">Service</th>
            <th scope="col" className="number">
              Per month
            </th>
            <th scope="col">Assumptions</th>
          </tr>
        </thead>
        <tbody>
          {cost.lines.map((line) => (
            <tr key={line.resource}>
              <td>
                <code>{line.resource}</code>
              </td>
              <td>{serviceName(line.service)}</td>
              <td className="number">{line.priced ? usd(line.monthly_usd) : "not priced"}</td>
              <td>{line.assumptions.join(" ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {cost.notes.map((note) => (
        <p key={note} className="muted">
          {note}
        </p>
      ))}
    </>
  );
}

/** One review, in the order a reader needs it: security first, then money, then details. */
export function Report({ report }: { report: ReviewReport }) {
  const security = report.findings.filter((f) => f.category === "security");
  // A finding with a rule id is made by code. Outside security that is the budget check,
  // which compares the estimate with the budget saved for the project. Only findings
  // without a rule id are written by the AI model.
  const fromBudget = report.findings.filter((f) => f.category !== "security" && f.rule_id);
  const suggestions = report.findings.filter((f) => f.category !== "security" && !f.rule_id);
  const seconds = report.timings.total;
  return (
    <div className="report">
      <section className="panel" aria-label="Review result">
        <h2>{report.headline}</h2>
        {report.summary && <p>{report.summary}</p>}
        {report.warnings.map((warning) => (
          <p key={warning} className="notice">
            {warning}
          </p>
        ))}
      </section>

      <section className="panel" aria-labelledby="security-title">
        <h3 id="security-title">Security findings</h3>
        <p className="muted">
          These come from fixed rules, not from the AI model. The same file always gives the same
          findings, and your feedback cannot hide or lower them.
        </p>
        {security.length === 0 ? (
          <p>No security rule fired on this file.</p>
        ) : (
          <ul className="findings">
            {security.map((finding, index) => (
              <FindingCard key={`${finding.rule_id}-${index}`} finding={finding} />
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="suggestions-title">
        <h3 id="suggestions-title">Suggestions for cost and simpler setups</h3>
        <p className="muted">
          These are written by an AI model ({report.model}). Each one should link to the Google
          Cloud documentation it is based on. Check them before you act.
        </p>
        {suggestions.length === 0 ? (
          <p>No suggestions for this file.</p>
        ) : (
          <ul className="findings">
            {suggestions.map((finding, index) => (
              <FindingCard key={`${finding.resource}-${index}`} finding={finding} />
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="cost-title">
        <h3 id="cost-title">Cost estimate</h3>
        {fromBudget.map((finding) => (
          <div key={finding.issue} className="notice">
            <p>
              <strong>{finding.issue}</strong> {finding.recommendation}
            </p>
            <p className="muted">
              This comes from the budget you saved for this project, not from the AI model.
            </p>
          </div>
        ))}
        <Cost cost={report.cost_estimate} />
      </section>

      {report.unsupported_resources.length > 0 && (
        <section className="panel" aria-labelledby="skipped-title">
          <h3 id="skipped-title">Not reviewed</h3>
          <p className="muted">These resource types are outside the five supported services.</p>
          <ul>
            {report.unsupported_resources.map((resource) => (
              <li key={resource}>
                <code>{resource}</code>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel details" aria-labelledby="run-title">
        <h3 id="run-title">About this review</h3>
        <ul>
          <li>Resources reviewed: {report.resources_reviewed}</li>
          <li>
            AI model calls: {report.usage.llm_calls} (tokens:{" "}
            {report.usage.input_tokens.toLocaleString("en-US")} in,{" "}
            {report.usage.output_tokens.toLocaleString("en-US")} out)
          </li>
          <li>
            AI cost of this review:{" "}
            {report.usage.cost_usd == null
              ? "unknown for this model"
              : usd(report.usage.cost_usd, 4)}
          </li>
          {seconds !== undefined && <li>Time taken: {seconds.toFixed(1)} seconds</li>}
        </ul>
      </section>
    </div>
  );
}
