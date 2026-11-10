---
title: Spot VMs in GKE
service: gke
source_url: https://cloud.google.com/kubernetes-engine/docs/concepts/spot-vms
---

## What they are

GKE node pools can run on Spot VMs, which cost much less than standard VMs but can be reclaimed by Compute Engine at any time. GKE adds a label and can add a taint to Spot nodes so you can control which workloads are scheduled on them.

## How to use them safely

Run stateless, batch and fault-tolerant workloads on a Spot node pool, and keep a standard node pool for system components and workloads that must not be interrupted. Use pod disruption budgets and several replicas so a preemption does not take a service down. Spot capacity is not guaranteed, so do not rely on it for the only copy of a critical service.
