---
title: Workload Identity Federation for GKE
service: gke
source_url: https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity
---

## What it does

Workload Identity Federation for GKE lets a Kubernetes service account act as an IAM principal. Pods then call Google Cloud APIs with their own identity and permissions, without exported service account keys and without borrowing the node's service account.

## Why it matters

Without it, every pod on a node can use the node service account, so one compromised pod gets every permission the node has. With it, each workload gets only the roles it needs. It is enabled on a cluster by setting a workload pool, and is always enabled on Autopilot clusters.
