"use client";

import { useEffect, useState } from "react";

import { AdvancedSettings, DEFAULT_ADVANCED, toOptions } from "./AdvancedSettings";
import { FeedbackForm } from "./FeedbackForm";
import { Intro } from "./Intro";
import { Progress } from "./Progress";
import { ProjectMemory } from "./ProjectMemory";
import { Report } from "./Report";
import { getCapabilities, getSample, getSamples, sendFeedback, streamReview } from "@/lib/api";
import type { Capabilities, FeedbackChoice, ReviewReport } from "@/lib/types";

const PROJECT_NAME = /^[A-Za-z0-9_.-]{1,64}$/;
const API_DOWN =
  "The review service is not answering. Start the Python API with " +
  "“uv run python -m api.server” and reload this page.";

/** The whole screen: explain, take Terraform, show progress, show the report, take feedback. */
export function ReviewApp() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [samples, setSamples] = useState<string[]>([]);
  const [project, setProject] = useState("default");
  const [terraform, setTerraform] = useState("");
  const [advanced, setAdvanced] = useState(DEFAULT_ADVANCED);
  const [steps, setSteps] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [problem, setProblem] = useState("");
  const [finished, setFinished] = useState("");

  useEffect(() => {
    getCapabilities()
      .then(setCapabilities)
      .catch(() => setProblem(API_DOWN));
    getSamples()
      .then(setSamples)
      .catch(() => setSamples([]));
  }, []);

  const projectIsValid = PROJECT_NAME.test(project);

  const chooseSample = async (name: string) => {
    if (!name) return;
    try {
      setTerraform(await getSample(name));
    } catch {
      setProblem("Could not load that example.");
    }
  };

  const chooseFile = async (file: File | undefined) => {
    if (!file || !capabilities) return;
    if (file.size > capabilities.max_input_kb * 1000) {
      setProblem(`That file is larger than ${capabilities.max_input_kb} KB.`);
      return;
    }
    setProblem("");
    setTerraform(await file.text());
  };

  const review = async () => {
    setProblem("");
    setFinished("");
    setReport(null);
    setSteps([]);
    setRunning(true);
    const request = { terraform, project_id: project, options: toOptions(advanced) };
    for await (const event of streamReview(request)) {
      if (event.type === "step" && event.step) {
        const step = event.step;
        setSteps((done) => [...done, step]);
      } else if (event.type === "report" && event.report) {
        setReport(event.report);
        setWaiting(Boolean(event.waiting_for_feedback));
      } else {
        setProblem(event.message ?? "The review did not finish.");
      }
    }
    setRunning(false);
  };

  const finish = async (feedback: FeedbackChoice[]) => {
    if (!report) return;
    try {
      const result = await sendFeedback(report.review_id, feedback);
      setWaiting(false);
      setFinished(
        result.saved > 0
          ? "Feedback saved. It will be used in the next review of this project."
          : "Review finished and saved to this project's history.",
      );
    } catch {
      setProblem("Could not save your feedback. The review may already be finished.");
    }
  };

  return (
    <div className="layout">
      <main>
        <header>
          <h1>GCP Infra Review</h1>
          <p className="lead">
            Check Terraform for Google Cloud before you apply it: security, monthly cost and
            cheaper alternatives.
          </p>
        </header>

        {capabilities && <Intro capabilities={capabilities} />}

        <section className="panel" aria-labelledby="input-title">
          <h2 id="input-title">Your Terraform</h2>
          <div className="row">
            <label>
              Start from an example (optional)
              <select defaultValue="" onChange={(event) => chooseSample(event.target.value)}>
                <option value="">(none)</option>
                {samples.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Or upload a .tf file
              <input
                type="file"
                accept=".tf"
                onChange={(event) => chooseFile(event.target.files?.[0])}
              />
            </label>
          </div>
          <label>
            Terraform
            <textarea
              rows={14}
              spellCheck={false}
              value={terraform}
              onChange={(event) => setTerraform(event.target.value)}
              placeholder='resource "google_storage_bucket" "example" { ... }'
            />
          </label>
          <button
            type="button"
            className="primary"
            onClick={review}
            disabled={running || !terraform.trim() || !projectIsValid}
          >
            Review
          </button>
        </section>

        {problem && (
          <p role="alert" className="alert">
            {problem}
          </p>
        )}

        {(running || steps.length > 0) && <Progress steps={steps} running={running} />}

        {report && <Report report={report} />}
        {report && waiting && <FeedbackForm report={report} onSubmit={finish} />}
        {finished && (
          <p role="status" className="success">
            {finished}
          </p>
        )}
      </main>

      <aside aria-label="Project and settings">
        <label>
          Project
          <input
            type="text"
            maxLength={64}
            value={project}
            onChange={(event) => setProject(event.target.value.trim())}
            aria-invalid={!projectIsValid}
          />
        </label>
        {!projectIsValid && (
          <p className="muted">Use letters, digits, dot, dash or underscore (1 to 64).</p>
        )}
        {projectIsValid && <ProjectMemory project={project} />}
        <AdvancedSettings
          value={advanced}
          defaultModel={capabilities?.model ?? "the configured model"}
          onChange={setAdvanced}
        />
      </aside>
    </div>
  );
}
