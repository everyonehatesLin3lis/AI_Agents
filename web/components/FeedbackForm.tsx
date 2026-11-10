"use client";

import { useState } from "react";

import type { FeedbackAction, FeedbackChoice, ReviewReport } from "@/lib/types";

type Answer = { action: FeedbackAction | "none"; comment: string };

const CHOICES: { value: Answer["action"]; label: string }[] = [
  { value: "none", label: "No feedback" },
  { value: "helpful", label: "Helpful" },
  { value: "dismiss", label: "Not relevant for this project" },
];

/**
 * The human review step. Only AI suggestions can be rated: security findings and the
 * budget check (both made by code) are not offered here. The server also ignores any
 * feedback about a security finding, whatever a client sends.
 */
export function FeedbackForm({
  report,
  onSubmit,
}: {
  report: ReviewReport;
  onSubmit: (feedback: FeedbackChoice[]) => void;
}) {
  const rateable = report.findings
    .map((finding, index) => ({ finding, index }))
    .filter(({ finding }) => finding.category !== "security" && !finding.rule_id);
  const [answers, setAnswers] = useState<Record<number, Answer>>({});

  const answerFor = (index: number): Answer => answers[index] ?? { action: "none", comment: "" };
  const update = (index: number, change: Partial<Answer>) =>
    setAnswers((current) => ({ ...current, [index]: { ...answerFor(index), ...change } }));

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const feedback: FeedbackChoice[] = [];
    for (const { index } of rateable) {
      const answer = answerFor(index);
      if (answer.action !== "none") {
        feedback.push({ finding_index: index, action: answer.action, comment: answer.comment });
      }
    }
    onSubmit(feedback);
  };

  return (
    <section className="panel" aria-labelledby="feedback-title">
      <h3 id="feedback-title">Your feedback</h3>
      <p className="muted">
        Your answers are remembered for this project. A suggestion you mark as not relevant is
        moved down next time. Feedback never changes security findings.
      </p>
      <form onSubmit={submit}>
        {rateable.length === 0 && <p>There are no suggestions to rate.</p>}
        {rateable.map(({ finding, index }) => (
          <fieldset key={index} className="rate">
            <legend>
              <code>{finding.resource}</code>: {finding.issue}
            </legend>
            {CHOICES.map((choice) => (
              <label key={choice.value}>
                <input
                  type="radio"
                  name={`feedback-${index}`}
                  checked={answerFor(index).action === choice.value}
                  onChange={() => update(index, { action: choice.value })}
                />{" "}
                {choice.label}
              </label>
            ))}
            <label className="comment">
              Comment (optional)
              <input
                type="text"
                maxLength={300}
                value={answerFor(index).comment}
                onChange={(event) => update(index, { comment: event.target.value })}
              />
            </label>
          </fieldset>
        ))}
        <button type="submit">Finish review</button>
      </form>
    </section>
  );
}
