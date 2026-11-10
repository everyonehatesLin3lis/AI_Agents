# 06: Project memory and human feedback

**What to build:** A project's budget, region and preferences are remembered and used in every review. After a review the user rates the cost and sizing suggestions. A dismissed suggestion is deprioritised next time. Security findings are never affected.

**Blocked by:** 04

**Status:** done

- [x] Constraints are loaded into the state at the start of a review
- [x] A total above the budget produces a finding
- [x] The graph pauses at human_review and resumes with the feedback
- [x] Dismissing a security finding has no effect on the next review
- [x] Feedback for one project does not affect another

**Review talking point:** Two kinds of memory: the graph state lasts one review, the SQLite store lasts between reviews. Feedback can lower the priority of advice but can never switch off a security finding.
