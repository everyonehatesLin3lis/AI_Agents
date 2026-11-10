# Eval dataset

Fixed Terraform samples and their ground truth (`expected.json`). The dataset does not
change between runs, so results from different models and dates can be compared.

| Group | Files | What it tests |
|---|---|---|
| `vulnerable/` | 5 (one per service) | Rules fire on real problems (recall) |
| `clean/` | 5 (one per service) | Rules stay quiet on good configs (precision, zero critical false positives) |
| `mixed/` | 1 | Several services together, a `count`, an unsupported resource type |
| `injection/` | 3 | Instructions hidden in comments and strings must not change the findings |

## How the expected costs were calculated

All sums use `tools/prices_static.json`, 730 hours per month, default region
`us-central1`. They were worked out by hand, not by running the estimator, so the test
can disagree with the code.

**vulnerable/gcs_public.tf**: 100 GB × $0.02 = **$2.00**

**vulnerable/sql_open.tf**: `db-custom-2-7680` = 2 vCPU, 7.5 GB.
(2 × 0.0413 + 7.5 × 0.007) × 730 = 0.1351 × 730 = 98.623.
Storage 100 GB × 0.17 = 17.00. Sum 115.623, doubled for REGIONAL = **$231.25**

**vulnerable/compute_open_ssh.tf**: `n2-standard-4` = 4 vCPU, 16 GB.
(4 × 0.031611 + 16 × 0.004237) × 730 = 0.194236 × 730 = 141.792.
Disk 50 GB pd-ssd × 0.17 = 8.50. Total **$150.29**

**vulnerable/cloud_run_public_secret.tf**: 2 min instances, 2 vCPU, 1 GiB, idle rate.
(2 × 0.0000025 + 1 × 0.0000025) × 2 × 2,628,000 s = **$39.42**

**vulnerable/gke_insecure.tf**: fee 0.10 × 730 = 73.00. Regional cluster, 1 node per
zone × 3 zones. `e2-standard-4`: (4 × 0.021811 + 16 × 0.002923) × 730 = 97.829, plus
100 GB pd-balanced = 10.00, so 107.829 per node × 3 = 323.486. Total **$396.49**

**clean/gcs_clean.tf**: 100 GB NEARLINE × 0.01 × 1.1 (europe-west1) = **$1.10**

**clean/sql_clean.tf**: `db-custom-1-3840` = 1 vCPU, 3.75 GB, europe-west1 (× 1.1).
(0.0413 + 3.75 × 0.007) × 1.1 × 730 = 54.243. Storage 20 × 0.17 × 1.1 = 3.74.
Total **$57.98**

**clean/compute_clean.tf**: `e2-medium` = 1 vCPU, 4 GB.
(0.021811 + 4 × 0.002923) × 730 = 24.457. Disk 20 GB pd-balanced = 2.00. Total **$26.46**

**clean/cloud_run_clean.tf**: min instances 0, so no fixed cost: **$0.00**

**clean/gke_clean.tf**: fee 73.00 (default pool removed). Zonal pool, 2 nodes of
`e2-standard-2`: (2 × 0.021811 + 8 × 0.002923) × 730 = 48.914, plus default 100 GB
pd-balanced = 10.00, so 58.914 × 2 = 117.83. Total **$190.83**

**mixed/web_stack.tf**:
- 2 × `e2-standard-2` in europe-west1: (0.067006 × 1.1 × 730 + 30 × 0.10 × 1.1) × 2 =
  (53.806 + 3.30) × 2 = 114.21
- `db-f1-micro` in europe-west1: 0.0105 × 1.1 × 730 + 10 × 0.17 × 1.1 = 8.432 + 1.87 = 10.30
- 100 GB COLDLINE (location `EU` is not a region, so default region): 0.40
- Total **$124.91**

The injection samples have no expected cost: they test security behaviour only.
