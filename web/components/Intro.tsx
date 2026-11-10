import { serviceName } from "@/lib/labels";
import type { Capabilities } from "@/lib/types";

/** The first thing a visitor reads: what the tool does, for which services, and its limits. */
export function Intro({ capabilities }: { capabilities: Capabilities }) {
  return (
    <section className="panel intro" aria-labelledby="intro-title">
      <h2 id="intro-title">What this tool does</h2>
      <p>
        Paste a Terraform file for Google Cloud and get a review <strong>before</strong> you run{" "}
        <code>terraform apply</code>. The review has three parts:
      </p>
      <ol>
        <li>
          <strong>Security findings</strong> from {capabilities.rule_count} fixed security rules.
          The same file always gives the same findings.
        </li>
        <li>
          <strong>An estimated monthly cost</strong> for each resource, with the assumptions
          behind it.
        </li>
        <li>
          <strong>Suggestions for cheaper or simpler setups</strong>, written by an AI model, each
          with a link to the Google Cloud documentation it is based on.
        </li>
      </ol>

      <p className="label">Supported services</p>
      <ul className="chips">
        {capabilities.services.map((id) => (
          <li key={id}>{serviceName(id)}</li>
        ))}
      </ul>

      <p className="safe">
        It only reads the text you paste. It never creates, changes or deletes anything in your
        Google Cloud project, and it needs no Google Cloud login.
      </p>

      {!capabilities.llm_configured && (
        <p className="notice" role="status">
          No AI model is configured, so you will get the security findings and the cost estimate,
          but no suggestions.
        </p>
      )}

      <details>
        <summary>What it does not do</summary>
        <ul>
          <li>
            Other Google Cloud services (Pub/Sub, BigQuery, IAM roles, load balancers and so on)
            are listed in the report as not reviewed.
          </li>
          <li>
            Variables, modules and expressions are not worked out. A value that is not written
            in the file is treated as unknown.
          </li>
          <li>It does not look at a running project, only at the file.</li>
          <li>
            The cost is a list-price estimate. Traffic, data transfer and discounts are not
            included.
          </li>
          <li>
            Files over {capabilities.max_input_kb} KB, and text that is not Terraform, are
            rejected.
          </li>
          <li>It does not rewrite your Terraform. You decide what to change.</li>
        </ul>
      </details>
    </section>
  );
}
