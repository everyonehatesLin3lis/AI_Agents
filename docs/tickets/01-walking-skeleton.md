# 01: Walking skeleton: Terraform in, one finding shown in the UI

**What to build:** A user pastes Terraform with a public bucket into the Streamlit page, presses Review and sees a critical finding. The path runs through every layer: input validation, parser, one security rule, a minimal graph, the report and the UI.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Pasting the public-bucket sample shows a critical GCS-001 finding
- [x] Input that is not Terraform shows a clear error and nothing else runs
- [x] A UI test covers the path with Streamlit's AppTest

**Review talking point:** The first thing built was the thinnest path through every layer, not one finished layer. It proves the pieces fit together before any of them is made complete.
