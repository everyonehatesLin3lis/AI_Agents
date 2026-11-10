# 05: Prompt injection cannot change the review

**What to build:** Instructions hidden in comments, descriptions, labels or environment values in the Terraform do not change the findings and do not appear in the report.

**Blocked by:** 04

**Status:** done

- [x] Three injection samples keep all their expected security findings
- [x] A test with an LLM that obeys the injected text still gives a correct report
- [x] Injected text never appears in any prompt
- [x] Links outside Google Cloud documentation are removed from LLM output
- [x] The LLM cannot emit a security finding or a critical severity

**Review talking point:** The file under review is untrusted data. The model is never shown the raw file, and it has no way to alter security findings, so there is nothing for an injection to achieve.
