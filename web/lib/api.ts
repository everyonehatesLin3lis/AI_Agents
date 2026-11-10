// The only place the UI talks to the Python API. Paths start with /api and are forwarded
// to the Python server by the rewrite in next.config.ts.

import type {
  Capabilities,
  FeedbackChoice,
  FinishResult,
  ProjectMemory,
  ReviewEvent,
  ReviewRequest,
} from "./types";

const UNREACHABLE =
  "Could not reach the review service. Check that the Python API is running " +
  "(uv run python -m api.server) and try again.";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} answered ${response.status}`);
  return (await response.json()) as T;
}

async function sendJson<T>(path: string, method: "POST" | "PUT", body: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path} answered ${response.status}`);
  return (await response.json()) as T;
}

export const getCapabilities = () => getJson<Capabilities>("/api/capabilities");

export const getSamples = async () =>
  (await getJson<{ samples: string[] }>("/api/samples")).samples;

export const getSample = async (name: string) =>
  (await getJson<{ terraform: string }>(`/api/samples/${name}`)).terraform;

export const getMemory = (project: string) =>
  getJson<ProjectMemory>(`/api/projects/${encodeURIComponent(project)}/memory`);

export const saveMemory = (project: string, memory: ProjectMemory) =>
  sendJson<ProjectMemory>(`/api/projects/${encodeURIComponent(project)}/memory`, "PUT", memory);

export const sendFeedback = (reviewId: string, feedback: FeedbackChoice[]) =>
  sendJson<FinishResult>(`/api/reviews/${encodeURIComponent(reviewId)}/feedback`, "POST", {
    feedback,
  });

/**
 * Run a review. The API answers with one JSON event per line, sent as each step finishes,
 * so this yields events while the review is still running. A request that fails becomes
 * one `error` event, so the screen has a single way to show problems.
 */
export async function* streamReview(request: ReviewRequest): AsyncGenerator<ReviewEvent> {
  let response: Response;
  try {
    response = await fetch("/api/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    yield { type: "error", message: UNREACHABLE };
    return;
  }
  if (!response.ok || !response.body) {
    const invalid = response.status === 422;
    yield {
      type: "error",
      message: invalid
        ? "The request was not accepted. Check the project name and the size of the file."
        : UNREACHABLE,
    };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  for (;;) {
    const { done, value } = await reader.read();
    pending += decoder.decode(value, { stream: !done });
    const lines = pending.split("\n");
    pending = lines.pop() ?? ""; // the last piece may be half a line
    for (const line of lines) {
      if (line.trim()) yield JSON.parse(line) as ReviewEvent;
    }
    if (done) break;
  }
  if (pending.trim()) yield JSON.parse(pending) as ReviewEvent;
}
