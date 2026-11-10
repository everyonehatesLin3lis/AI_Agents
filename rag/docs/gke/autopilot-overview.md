---
title: GKE Autopilot overview
service: gke
source_url: https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview
---

## What Autopilot is

Autopilot is a GKE mode in which Google manages the nodes, scaling, upgrades and security configuration. You deploy workloads and Google provisions capacity for them. Autopilot applies many hardening settings by default, including Workload Identity Federation for GKE and Shielded GKE Nodes.

## Cost model

In Autopilot you pay for the CPU, memory and storage that your pods request, not for whole nodes. Idle node capacity and system overhead are not billed to you, so Autopilot is usually cheaper for small or variable workloads and for teams that would otherwise leave nodes partly empty. Large, steady, tightly packed workloads can be cheaper on Standard mode, where you pay per node.
