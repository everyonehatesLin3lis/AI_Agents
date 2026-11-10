# 03: Monthly cost estimate with visible assumptions

**What to build:** The report shows an estimated monthly cost per resource and in total. Each line lists the assumptions behind it. When live prices are not available the report says prices may be outdated.

**Blocked by:** 01

**Status:** done

- [x] Totals match the hand-calculated values for 11 samples
- [x] Unknown machine types are shown as not priced, never guessed
- [x] Billing API client has a timeout, retries with backoff and falls back to static prices
- [x] The API key never appears in an error message

**Review talking point:** Every external call has a timeout, a retry and a fallback. If the pricing API is down the review still works and tells the user what it could not check.
