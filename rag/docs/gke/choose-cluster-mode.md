---
title: GKE cluster fee and choosing a mode of operation
service: gke
source_url: https://cloud.google.com/kubernetes-engine/docs/concepts/choose-cluster-mode
---

## Standard and Autopilot

GKE has two modes. In Standard mode you create and manage node pools and pay for every node, used or not. In Autopilot mode Google manages the nodes and you pay for pod requests. Autopilot is the recommended default, and Standard is for cases that need specific node configuration or control.

## Fixed costs to remember

Every cluster has a cluster management fee charged per hour, in both modes, in addition to the compute it uses. A regional cluster runs its nodes in several zones, so a node count of 1 per zone means three nodes. For a few small services, one shared cluster, or Cloud Run with no cluster at all, is often simpler and cheaper than a dedicated cluster per application or environment.
