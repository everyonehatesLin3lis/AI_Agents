---
title: Service accounts for VMs
service: compute
source_url: https://cloud.google.com/compute/docs/access/service-accounts
---

## Default service account

Every project has a Compute Engine default service account, and VMs use it unless another one is specified. Depending on organization policy it is automatically granted the Editor role, which gives very broad access to the project. A VM that runs as this account with the cloud-platform scope can change almost any resource if it is compromised.

## Recommendation

Create a user-managed service account for each workload and grant it only the IAM roles it needs. Attach it to the VM, set the cloud-platform access scope, and control access with IAM roles. Access scopes are a legacy mechanism, and IAM roles on a dedicated account are the recommended way to limit what a VM can do.
