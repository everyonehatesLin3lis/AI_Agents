# GCP infrastructure review

**2 security finding(s): 1 medium, 1 low. Estimated cost: $124.32/month.**

The AI summary and recommendations are not available for this review. The security findings and the cost estimate below were produced by code and are complete.

> Warning: Billing API not used: No GCP_BILLING_API_KEY configured.
> Warning: Research planning used default queries: No LLM is configured (missing API key).
> Warning: Document grading skipped, all results kept: No LLM is configured (missing API key).
> Warning: AI recommendations unavailable: No LLM is configured (missing API key).
> Warning: Prices may be outdated: the static price table was used.
> Warning: 1 resource(s) are of an unsupported type and were not reviewed.

## Security findings

### [MEDIUM] SQL-004 `google_sql_database_instance.db`
- **Issue:** Automated backups are off. Automated backups are not enabled.
- **In your Terraform:** `settings.backup_configuration.enabled is not set`
- **Recommendation:** Enable backup_configuration (and point-in-time recovery for production data).
- **Source:** https://cloud.google.com/sql/docs/mysql/backup-recovery/backups

### [LOW] GCS-004 `google_storage_bucket.uploads`
- **Issue:** Object versioning is off. Object versioning is off, so overwritten or deleted objects cannot be recovered.
- **In your Terraform:** `versioning.enabled is not set`
- **Recommendation:** Enable versioning (with a lifecycle rule to expire old versions) for important data.
- **Source:** https://cloud.google.com/storage/docs/object-versioning

## Cost estimate

Total: **$124.32 per month** (price source: static, priced in: europe-west1, us-central1)

| Resource | USD/month | Assumptions |
|---|---:|---|
| `google_compute_instance.app` | 113.62 | e2-standard-2 running 730 h/month in europe-west1. Boot disk 30 GB pd-balanced. count = 2. |
| `google_sql_database_instance.db` | 10.30 | db-f1-micro running 730 h/month in europe-west1. Storage 10 GB SSD. |
| `google_storage_bucket.uploads` | 0.40 | Location 'EU' is a multi-region: priced as us-central1 (approximate). Assumed 100 GB stored (COLDLINE). Terraform does not say how much data a bucket holds. Operations and network egress are not included. |

- Prices may be outdated: the static price table was used.

## Not reviewed (unsupported resource types)

- `google_pubsub_topic.events`

_Model: none. LLM calls: 0. Tokens: 0 in / 0 out. LLM cost: $0.0000._
