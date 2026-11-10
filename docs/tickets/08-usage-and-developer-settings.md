# 08: Token usage, cost and timing per review; Developer settings

**What to build:** Every review shows how many tokens it used, what that cost and how long each step took. Model, temperature and prompt additions are in a separate Developer section of the UI.

**Blocked by:** 04

**Status:** done

- [x] Tokens and LLM calls are recorded per node and summed in the report
- [x] Time per node and in total is recorded
- [x] A model with an unknown price shows the cost as n/a
- [x] Developer settings sit in their own section and cannot affect the security rules

**Review talking point:** You cannot manage what you do not measure. Recording tokens and time per step shows where the money and the seconds go, which is what the model comparison is built on.
