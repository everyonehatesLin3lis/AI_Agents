# GCP infrastructure review

**2 security finding(s): 1 medium, 1 low. Estimated cost: $124.32/month.**

This configuration provisions two compute instances, a Cloud SQL database instance, a Cloud Storage bucket, and a firewall. Security findings have been detected on the database and storage bucket resources. The main driver of the cost is the pair of compute instances.

> Warning: 1 resource(s) are of an unsupported type and were not reviewed.

## Security findings

### [MEDIUM] SQL-004 `google_sql_database_instance.db`
- **Issue:** Automated backups are off. Automated backups are not enabled.
- **Recommendation:** Enable backup_configuration (and point-in-time recovery for production data).
- **Source:** https://cloud.google.com/sql/docs/mysql/backup-recovery/backups

### [LOW] GCS-004 `google_storage_bucket.uploads`
- **Issue:** Object versioning is off. Object versioning is off, so overwritten or deleted objects cannot be recovered.
- **Recommendation:** Enable versioning (with a lifecycle rule to expire old versions) for important data.
- **Source:** https://cloud.google.com/storage/docs/object-versioning

## Cost and sizing recommendations

### [MEDIUM] `google_compute_instance.app`
- **Issue:** A small web service running on dedicated VMs can often be moved to Cloud Run to eliminate operating system patching and node management.
- **Recommendation:** Consider migrating the stateless web service from Compute Engine instances to Cloud Run.
- **Source:** https://cloud.google.com/run/docs/overview/what-is-cloud-run

## Cost estimate

Total: **$124.32 per month** (price source: billing_api, priced in: europe-west1, us-central1)

| Resource | USD/month | Assumptions |
|---|---:|---|
| `google_compute_instance.app` | 113.62 | e2-standard-2 running 730 h/month in europe-west1. Boot disk 30 GB pd-balanced. count = 2. |
| `google_sql_database_instance.db` | 10.30 | db-f1-micro running 730 h/month in europe-west1. Storage 10 GB SSD. |
| `google_storage_bucket.uploads` | 0.40 | Location 'EU' is a multi-region: priced as us-central1 (approximate). Assumed 100 GB stored (COLDLINE). Terraform does not say how much data a bucket holds. Operations and network egress are not included. |


## Not reviewed (unsupported resource types)

- `google_pubsub_topic.events`

_Model: google/gemini-3.5-flash-lite. LLM calls: 3. Tokens: 4413 in / 311 out. LLM cost: $0.0021._