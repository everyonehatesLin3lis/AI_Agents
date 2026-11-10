---
title: Harden your GKE cluster
service: gke
source_url: https://cloud.google.com/kubernetes-engine/docs/how-to/hardening-your-cluster
---

## Access control

Leave legacy attribute-based access control (ABAC) disabled and use Kubernetes RBAC with IAM. Legacy ABAC grants broad static permissions and is kept only for backward compatibility. Give users and service accounts the least privilege they need.

## Node identity

Do not run nodes as the Compute Engine default service account, which usually has broad project permissions. Create a minimal service account for nodes with only the roles needed for logging, monitoring and pulling images, and use Workload Identity Federation for GKE so each workload has its own identity. Also keep the cluster upgraded, use Shielded GKE Nodes and restrict access to the control plane.
