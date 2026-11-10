# 07: MCP tool for coding agents

**What to build:** A coding agent calls review_gcp_infra with Terraform text and gets back the report as Markdown and as JSON in a single call. Bad input and failures come back as clear messages.

**Blocked by:** 02, 03

**Status:** done

- [x] The server lists one tool with a description and input schema
- [x] A valid call returns findings, the cost estimate and Markdown
- [x] Non-Terraform input returns status rejected with the reason
- [x] An unexpected failure returns status error, never a stack trace

**Review talking point:** MCP is a standard way to hand a tool to an AI assistant. The intended use is one agent checking another agent's Terraform before it is applied.
