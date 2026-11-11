# Learning notes

Plain-language notes on each part of the project: what was built, why this way, what
else was possible and what can break. I wrote them so I can explain every decision in a
live review.

---

## Phase 1: Deterministic tools

**What was built.** Three tools that are ordinary Python with no AI in them:

- The **parser** turns Terraform text into a list of resources. Before parsing it
  checks that the input is really Terraform and is under 200 KB.
- The **security rules** are 20 small functions. Each looks at one resource and says
  "this is a problem because…" or nothing.
- The **cost estimator** multiplies quantities by prices: for a VM, vCPUs and memory
  times the hourly price times 730 hours, plus the disk.

**Why this way.** These questions have right answers. "Is `allUsers` in the member
list?" is not a matter of opinion, so asking an LLM would only add cost, delay and a
chance of being wrong. Code gives the same answer every time and you can point at the
line that produced it.

**Alternatives.** Use an existing scanner such as Checkov or tfsec for security, or
Infracost for cost. Those are more complete. Writing a small version here keeps the
project self-contained and makes every rule explainable. In a real product you would
wrap the existing tools.

**What can break.**
- Values that are only known at apply time (`var.region`, references to other
  resources). The tools do not evaluate expressions, so they treat these as unknown.
- New resource types or new attribute names in the Google provider.
- The static prices going out of date. That is why the report says so.

**Words to know.** *Deterministic*: same input, same output. *HCL*: the language
Terraform files are written in. *SKU*: one priced item in Google's price list.

---

## Phase 2: RAG

**What was built.** A small library of notes on Google Cloud documentation pages, and
a search over it. `ingest.py` splits each note into sections, turns each section into
a vector (a list of numbers that represents its meaning) and stores it in Chroma.
`search_gcp_docs` turns a question into a vector and returns the closest sections.

**Why this way.** An LLM on its own will happily state "facts" about GCP that are out
of date or invented. RAG (retrieval-augmented generation) gives it real text to work
from, and every piece of text carries the URL of the page it came from. That is what
lets the report cite a source.

**Alternatives.** Let the LLM search the web live (slower, less predictable, and the
results change from day to day). Fine-tune a model on the docs (expensive, and it
still could not cite). Put all the docs in the prompt (works for 34 pages, not for
3,400, and costs tokens on every call).

**What can break.**
- The search returns the nearest text, which is not always relevant text. That is why
  the next step, grading, exists.
- If the answer is not in the library, nothing can find it.
- The notes can drift from what Google's pages say today.

**Words to know.** *Embedding*: the vector for a piece of text. *Chunk*: one stored
piece of a document. *Hit rate at k*: how often the right document is in the top k
results.

---

## Phase 3: Memory

**What was built.** A SQLite file with three tables: what we know about each project
(budget, region, preferences), the feedback the user has given, and a history of
reviews. Plus one small file, `feedback_policy.py`, that decides what feedback is
allowed to change.

**Why this way.** The agent has two kinds of memory. *Short-term* memory is the graph
state: it exists for one review. *Long-term* memory is this database: it survives
between reviews, so the second review of a project already knows its budget and knows
which suggestions the user did not find useful.

The policy is deliberately tiny and separate. The rule "feedback can lower the
priority of a cost suggestion but can never touch a security finding" is the most
important safety property in the project, so it lives in one place that can be read in
a minute.

**Alternatives.** Store memory as free text and let the LLM read it (flexible, but
then memory becomes another way to inject instructions). Use a vector database for
memory (useful for large, fuzzy memories; overkill for a budget and a region).

**What can break.** A dismissal applies to a whole kind of suggestion for a resource
type, which is coarse. Feedback given by mistake stays until a later "helpful" on the
same kind cancels it.

---

## Phase 4: The agent graph

**What was built.** Ten nodes connected in a graph. Three are plain code, four use the
LLM, and three handle searching, the human pause and saving. The state is one Pydantic
object that every node reads and updates.

**Why a graph and not one big prompt.** One prompt that "reviews the Terraform" would
be a black box. Splitting the work means each step has one job, can fail on its own,
can be timed and tested on its own, and uses the LLM only if it needs judgment.

**The four LLM steps and why each needs an LLM.**
1. `plan_research` decides what is worth looking up. That depends on the whole
   picture: what is expensive, what looks oversized, what the project prefers.
2. `grade_docs` reads the search results and keeps the useful ones. Search finds
   similar words; a reader finds relevant meaning.
3. `rewrite_query` tries different wording when the search came back poor.
4. `write_report` writes the summary and turns documents into concrete advice.

**The loop.** If fewer than two useful documents are found, the queries are rewritten
and the search runs again. A counter in the state stops this after two rewrites. A loop
without a counter is the classic way an agent burns money, so the limit is checked in
a plain routing function, not left to the model.

**The pause.** `human_review` calls `interrupt()`. The graph stops, its state is saved
by a checkpointer, and the UI shows the report. When the user submits feedback the
graph resumes at the same node. This is "human in the loop".

**Guards on the LLM's output.** The LLM's answer is treated like user input: checked
before use.
- It must be valid JSON for a schema. One retry, then a fallback.
- The schema has no "security" category and no "critical" or "high" severity, so the
  LLM cannot raise an alarm that the rules did not.
- A recommendation about a resource that is not in the file is dropped.
- A source is accepted only if it is one of the documents that were retrieved.
- Links to anything except Google Cloud documentation are removed.
- A claimed saving is capped at what the resource costs.
- At the end, the security findings in the report are compared with the rule output.
  If they differ, the review fails loudly.

**What can break.**
- A model that ignores the JSON instruction. Handled by the retry and the fallback.
- A provider outage. Handled: the report still has the rule findings and the cost.
- A model that writes plausible but wrong advice from a real document. The guards
  cannot catch that. The faithfulness metric in the evals is there to measure it.

**Words to know.** *State*: the data passed between nodes. *Reducer*: the rule for
combining two updates to the same field (for example, append to the error list).
*Conditional edge*: a function that picks the next node. *Checkpointer*: where a
paused graph is saved. *Fallback*: what a step does when its main path fails.

---

## Phase 5: Interfaces

**What was built.** Two ways in. The **MCP server** exposes one tool,
`review_gcp_infra`, that a coding agent can call. The **web UI** is for people: paste
Terraform, watch the steps, read the report, give feedback. It was first built with
Streamlit and later rebuilt with Next.js (see "The web UI" below).

**Why MCP.** MCP (Model Context Protocol) is a standard way to give an AI assistant a
tool. Any MCP client can use the reviewer without custom glue. The intended use is a
coding agent calling the review on Terraform it has just written, before proposing to
apply it. So one agent checks another agent's work.

**Why the advanced settings are separate.** The model, the documentation search switch
and prompt additions are there for experiments. A normal user should not need them and
should not change them by accident. Nothing in that section can change the security
rules.

**Error handling.** Both interfaces turn every failure into a clear message. The MCP
tool returns `{"status": "rejected", "error": "..."}` and never a stack trace, because
the caller is another program that has to explain the problem to its user.

**What can break.** A paused review is held in memory, so restarting the API loses it.
The MCP tool waits for the whole review, which takes as long as the LLM calls take.

### The web UI: from Streamlit to Next.js (2026-11-10)

**What was built.** Three layers where there was one file:
1. `agent/service.py`, the *review service*: start a review, finish it with feedback,
   read and save project memory, list the examples, say what the tool supports.
2. `api/server.py`, an HTTP API (FastAPI) that only translates: a request becomes one
   service call, the result becomes JSON and a status code.
3. `web/`, a Next.js app (React, TypeScript). The browser talks to the Next.js server,
   which forwards `/api/*` to the Python API.

**Why a service in the middle.** The Streamlit file was not only a screen. It also
cached sessions, mapped errors to messages, built feedback items and saved project
memory. A JavaScript front end cannot call Python objects, so all of that had to cross
a network boundary. Putting it in one module first meant the HTTP layer stayed thin,
and the logic could be tested without a web server or a browser.

**How progress is shown live.** LangGraph can *stream*: it reports each node as it
finishes. The service turns that into events, the API sends one JSON object per line
(a format called NDJSON) as each event happens, and the browser reads the response as
it arrives. So the page can show "Checked the security rules" while the model is still
writing. One request, no polling.

**A safety detail worth saying out loud.** Feedback names a finding by its *position*
in the report, not by a key. The server looks the finding up itself, so a client cannot
invent a finding to dismiss, and the server ignores feedback about security findings
whatever is sent. The HTTP API has no login and listens on localhost only.

**What went wrong, and what it taught.** All the component tests passed, and the first
click on **Review** in a real browser crashed the page. The API left out empty fields
(`estimated_savings` was missing, not `null`), while the UI's test data had the field.
Both sides were tested, each against its own idea of the data. Three fixes: the API now
sends the report whole, the UI tolerates a missing value, and a test compares the field
names of the Python models with the TypeScript types. The lesson: tests on each side of
a boundary do not test the boundary. Run the real thing once.

**A second thing the real run showed.** The budget warning is made by code from the
budget saved for the project, but the first version of the page listed it under "written
by an AI model". Reading real output, not a fixture, is what caught it.

**What was given up.** Two processes to start instead of one, and two languages. The
TypeScript types are written by hand; the contract test catches a missing field, not a
wrong type.

---

## Phase 6: Evaluation

**What was built.** A fixed dataset with known right answers, a runner that measures
the agent against it and saves the raw results, and a script that turns saved results
into the README tables.

**Why two kinds of test.** `pytest` answers "is the code correct?" and uses a fake LLM,
so it is fast, free and never flaky. The evals answer "how good is the output?" and
need a real LLM, cost money and vary a little from run to run. Mixing them would make
the tests slow and unreliable.

**How to read the metrics.**
- *Precision*: of the findings reported, how many were right. Low precision means
  false alarms.
- *Recall*: of the real problems, how many were found. Low recall means misses.
- *F1*: one number that combines both.
- *Faithfulness*: does the text only say what its sources support? Scored by another
  LLM (the "judge").
- *Median and p95 latency*: the typical time, and the time 95% of reviews stay under.
  p95 shows the slow cases that an average hides.
- *Ablation*: switch one part off and see what changes. That is how you find out
  whether a part earns its cost.

**An honest caveat to say out loud.** The rules score perfectly on the dataset, and the
same person wrote both. That shows the rules do what they were designed to do. It does
not show how they do on other people's Terraform. A held-out test set is the fix, and
it is listed as future work.

**What can break.** LLM results vary between runs even at temperature 0, so each
sample is run several times. The judge is itself a model and can be wrong. Token
prices change, so each result file records the prices it used.

**First real runs (2026-11-10).** Three cheap models were compared, and RAG and the
rewrite loop were ablated on one of them. What came out, in plain words:
- *The security numbers are the same for every model*, because no model touches them.
  This is the strongest evidence that the "LLM cannot override security" design works.
- *Models differ in how much advice they give and how fast they are.* Gemini was about
  six times faster than MiMo but wrote about a quarter of the recommendations.
- *A saturated metric tells you nothing.* DeepEval faithfulness was 0.95 or higher for
  all three models, so it cannot rank them. A metric is only useful if it can tell
  options apart.
- *RAG is what makes recommendations citable*: without it, the same number of
  recommendations, none with a source.
- *A part that never runs cannot be measured.* The rewrite loop ran in 0 to 7% of
  reviews, because the document store was written for these exact samples. Proving it
  helps needs harder queries.
- *Noise is bigger than you expect.* Running the same configuration twice moved some
  numbers by 10%. Only differences much bigger than that mean anything.
- *Timeouts per attempt are not a deadline.* One review waited 628 seconds, because a
  60-second timeout was retried several times.

**A second agent, built to be compared (2026-11-10).** A ReAct agent was added in
`evals/` as a baseline: one LLM, real function calling, the same three tools, no checks
on its answer. Then both agents were run on the same samples. What came out:
- *The expected failure did not happen.* The idea was "a ReAct agent can be talked out
  of the security check". With Gemini it called the security tool every time and kept
  every real finding, also on the injection samples. Say this plainly in the review: the
  measurement did not confirm the fear on this dataset.
- *A different failure did happen.* The baseline wrote security findings of its own,
  with no rule behind them, on two clean files in every run (6 false positives). One
  saved example is a HIGH finding on a correct configuration. In the graph the LLM has
  no way to write a security finding at all.
- *Grading the search results matters.* Ragas context precision was 1.00 for the graph
  and 0.63 for the baseline, which keeps everything its search returns.
- *A test and an eval answer different questions.* The pytest test proves the baseline
  *can* return an empty report (with a fake model that obeys the injected text). The
  eval shows what a real model *did*. Both are true, and they are not the same claim.

**Ragas next to DeepEval.** Ragas measures the RAG step only: are the kept passages
useful (context precision), and is the advice supported by them (faithfulness).
- *A low score needs an explanation before a conclusion.* Ragas faithfulness was about
  0.5 for every model while DeepEval gave 0.95 or more. The first guess (the advice
  quotes cost numbers) was wrong; reading the saved text showed that. The second guess
  was tested: adding the facts about the reviewed resources to the context raised the
  score from 0.49 to 0.87. So the metric was mostly counting correct statements about
  the user's own file as "not in the documentation".
- *Do not change a metric after seeing its result.* The tables keep the first
  definition; the explanation and the check are reported next to it.
- *Save what was judged.* The first runs kept only scores, so adding Ragas meant paying
  for the reviews again. Records now keep the judged text, and `evals/rejudge.py` can
  score a saved run with another judge for the price of the judge alone.

**Checking prices against the real API paid off.** It found the static table charged
10% too much for disks in Europe. The fix stores exact prices, and the expected costs
in the dataset were recalculated by hand, not copied from the code, so the test can
still disagree with the code.

## Core concepts, explained with this project

### Function calling, and where it is in this project

**What function calling is.** The application gives the model a list of tools. Each
tool has a name, a description and a JSON Schema for its arguments. The model does not
run anything. It replies "call `get_weather` with `{"city": "Vilnius"}`". The
application checks the arguments, runs the function and sends the result back. The
model then answers or asks for another call. This loop is how a ReAct agent works.

**Where this project uses it: as the tool.** `mcp_server/server.py` exposes one
function, `review_gcp_infra(terraform: str, project_id: str = "default")`. The MCP SDK
turns its type hints and docstring into a tool schema. When Claude Code writes
Terraform, *its* model reads that schema, decides to call the tool, and fills in the
arguments. That is function calling, with this project on the receiving end. The
docstring is the tool's description, so it is written for a model: what the tool does,
what it returns and the 200 KB limit.

**Inside the agent: the same idea, with the graph in control.** The LLM still chooses
the arguments of a tool call, but it does not choose which tool runs or when:

| Step | The LLM chooses | Code runs |
|---|---|---|
| `plan_research` | search queries: `{"queries": [{"service": "cloud_sql", "query": "..."}]}` | `retrieve` calls `search_gcp_docs(query, service)` with them |
| `grade_docs` | which passages are relevant | the graph counts them and decides whether to loop |
| `rewrite_query` | better queries | `retrieve` runs again, at most 2 times |
| `write_report` | recommendations, each with a `source_url` | code checks every URL against the store |

The reply is validated against a Pydantic schema (`agent/llm.py`), which plays the
role of the tool's argument schema. Decision 4 explains why this is JSON mode and not
provider tool calling: it works the same across vendors on OpenRouter, it works with
the fake model in tests, and the schema is a guard (the report schema has no
"security" category, so the LLM cannot create or change a security finding).

**Tools that never go through the LLM.** `parse_terraform`, `check_security` and
`estimate_cost` are called directly by their nodes. A model choosing whether to run the
security check could skip it; fixed code cannot.

### Types of agents, and which one this is

| Type | How it works | Good for | Risk |
|---|---|---|---|
| Single LLM call (prompt engineering) | One prompt, one answer | Rewriting, summarising, classifying | No tools, no fresh facts |
| Chain or pipeline | Fixed steps, some of them LLM calls | Repeatable processes | Cannot adapt to the input |
| ReAct (reason + act) | The LLM loops: think, call a tool, read the result, repeat until done | Open tasks where the steps are unknown | Unpredictable path, cost and time; easy to talk into skipping a step |
| Plan-and-execute | One LLM call writes a plan, then the steps run | Long tasks with clear sub-steps | A bad plan is followed to the end |
| Router | An LLM picks one of several fixed paths | Mixed input types | Wrong route, wrong answer |
| Multi-agent | Several agents with roles hand work to each other | Large tasks needing different skills | Hard to debug and to evaluate |

**This project is a workflow agent: a fixed graph with bounded agentic steps.** It
mixes a pipeline (parse, security, cost always run, in order), plan-and-execute
(`plan_research` writes the queries, `retrieve` runs them), and a small self-correcting
loop (`grade_docs` judges the results, `rewrite_query` tries again, at most twice). That
loop is the "corrective RAG" pattern.

**Why not ReAct.** A review must always include the security check, cost the same order
of money each time, and finish in a known time. In a ReAct loop the model decides
whether to call each tool, so text hidden in the Terraform could persuade it to skip
the security tools, and the number of calls is open-ended. Here the order is fixed in
code and the model only fills in the parts that need judgement. The cost: the agent
cannot invent a new kind of step, for example looking at a service it has no tool for.

This was measured, not only argued: `evals/react_baseline.py` is a ReAct agent over the
same tools. With the model tested it did not skip the security tool, but it added
security findings of its own that no rule supports (see the Phase 6 notes and the
README results). In the baseline the function calling is the standard kind: the tools
are Python functions with a docstring, LangChain turns them into tool schemas, the
model replies with tool calls, and the loop runs them and feeds the results back.

### When to use prompt engineering, RAG or an agent

- **Prompt engineering** is enough when the model already knows what it needs, and the
  task is about the shape of the answer: format, tone, structure. Here every prompt in
  `agent/prompts/` uses it: a fixed role, the data wrapped in `<review_data>` tags and
  marked as untrusted, an exact JSON shape, and rules such as "only cite a URL from the
  passages given".
- **RAG** is needed when the answer must rest on facts the model may not know, may have
  wrong, or must cite: here, Google's current recommendations and their URLs. The
  ablation shows the effect: without RAG the model writes as many recommendations, but
  none can be traced to a source.
- **An agent** (a loop with decisions) is worth its cost when the steps depend on what
  is found. Here the model decides what to search for, based on what this file
  contains, and whether the results are good enough. A fixed query list would search
  for Cloud SQL tips on a file with no database.
- **Plain code** beats all three when the answer must be exact and repeatable:
  security rules and cost arithmetic. The model is used only where judgement is needed.

---

## Things a reviewer is likely to ask

**"Why not let the LLM do the security review?"** Because the answer must be the same
every time, explainable, and impossible to talk out of. Text hidden in the file cannot
persuade a regular expression.

**"How do you prevent prompt injection?"** Three layers: comments are dropped by the
parser; the LLM is shown a whitelist summary, not the file; and the LLM has no way to
change security findings whatever it reads. The dataset has three injection samples,
and the tests use a fake LLM that obeys the injected instructions to prove the report
is still correct.

**"What happens if OpenAI or OpenRouter is down?"** Each LLM step has a timeout,
retries and a fallback. The review returns the rule findings and the cost estimate,
with a warning that the advisory part is missing.

**"Is this an agent or a pipeline?"** Most of it is a fixed pipeline, on purpose. The
agentic parts are where the LLM chooses what to research, judges its own search
results, and decides to try again. The control flow around those choices is fixed
code, so the freedom is bounded.

**"What would you do with more time?"** A held-out dataset, real variable resolution,
more rules, and live prices for every service.

**"Which model would you use?"** For the UI and the MCP tool, Gemini 3.5 Flash Lite:
about 3 seconds per review against about 20 for the other two, the steadiest between
runs, every recommendation cited, and still a fraction of a cent. The security result does not depend on the
choice.

**"What does the LLM actually add?"** Without it the report already has every security
finding and the cost estimate, in a fifth of a second. The LLM adds two things: a
summary, and cost, sizing and simplification advice with a documentation link (for
example "this database is REGIONAL, which doubles the bill; ZONAL is enough for a test
system"). About six in ten of its recommendations name a value from my configuration;
the rest is general advice. It costs 3 to 20 seconds and a fraction of a cent. The
numbers come from `evals/llm_value.py`, which reuses the saved run and calls no model.

**"Why three model calls and not one?"** The first call decides what to look up, and the
search happens after it, so it cannot be merged with the writing call. Without the
search there is one call and half the time, but no recommendation has a source (the
`no_rag` ablation). The third call writes the text the user reads. The second call
(grading the search results) is the one I have not measured on its own: Ragas context
precision suggests it helps (1.00 against 0.63 for the baseline without it), but I have
not run the graph without it. I say that openly; it is under future work.

**"Your eval says the rules are perfect. Are they?"** No. They are perfect on 14 samples
I wrote next to the rules. Trying other common ways of writing the same resources found
a missed GKE finding (node pools declared inside the cluster were not checked) and
remediation text that did not fit the resource (MySQL links on a PostgreSQL instance,
v2 attribute names on a v1 Cloud Run service, "add this block" when the block was
there). Each is fixed and has a regression test. What I learned: a rule's advice can
depend on the resource, so a check may now return its own recommendation, and an eval
on my own samples only shows that the rules do what I already thought of.
