import { afterEach, describe, expect, it, vi } from "vitest";

import { streamReview } from "./api";
import type { ReviewEvent } from "./types";

function streamOf(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

async function collect(events: AsyncIterable<ReviewEvent>): Promise<ReviewEvent[]> {
  const all: ReviewEvent[] = [];
  for await (const event of events) all.push(event);
  return all;
}

afterEach(() => vi.unstubAllGlobals());

describe("streamReview", () => {
  it("yields one event per line, also when a line arrives in two pieces", async () => {
    const fetchMock = vi.fn(async () =>
      streamOf(['{"type":"step","step":"parse"}\n{"type":"st', 'ep","step":"security_check"}\n']),
    );
    vi.stubGlobal("fetch", fetchMock);

    const events = await collect(streamReview({ terraform: "resource {}", project_id: "shop" }));

    expect(events).toEqual([
      { type: "step", step: "parse" },
      { type: "step", step: "security_check" },
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reviews",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ terraform: "resource {}", project_id: "shop" }),
      }),
    );
  });

  it("turns a failed request into an error event the screen can show", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 502 })));

    const events = await collect(streamReview({ terraform: "x", project_id: "shop" }));

    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("error");
    expect(events[0].message).toMatch(/could not reach the review service/i);
  });
});
