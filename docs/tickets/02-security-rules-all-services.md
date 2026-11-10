# 02: Security rules for all five services

**What to build:** A review of any supported resource reports its security problems with a severity, a recommendation and a link to the Google Cloud page. Clean configurations produce no critical findings.

**Blocked by:** 01

**Status:** done

- [x] 20 rules across Cloud Storage, Cloud SQL, Compute Engine, Cloud Run and GKE
- [x] Every labelled sample in the dataset gives exactly its expected findings
- [x] Zero critical findings on the five clean samples
- [x] Resource types outside the scope are listed as not reviewed

**Review talking point:** Security checks are plain code because they have right answers. The same input always gives the same findings, and each finding can be traced to one small function.
