import { stepLabel } from "@/lib/labels";

/** The steps of a review as they finish, so a waiting user can see what is happening. */
export function Progress({ steps, running }: { steps: string[]; running: boolean }) {
  return (
    <section className="panel progress" aria-label="Review progress">
      <h2>What the review is doing</h2>
      <ol>
        {steps.map((step, index) => (
          <li key={`${step}-${index}`} className="done">
            {stepLabel(step)}
          </li>
        ))}
      </ol>
      {running && (
        <p role="status" className="working">
          Working on the next step…
        </p>
      )}
    </section>
  );
}
