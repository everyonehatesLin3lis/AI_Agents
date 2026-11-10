---
title: GKE cluster autoscaler
service: gke
source_url: https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler
---

## What it does

The cluster autoscaler changes the number of nodes in a node pool to match what the workloads need. It adds nodes when pods cannot be scheduled for lack of capacity, and removes nodes that are underused when their pods can run elsewhere. You set a minimum and a maximum size per node pool.

## Why it saves money

A node pool with a fixed node count is sized for peak load and is paid for all day. With autoscaling the pool shrinks when demand is low. It works on resource requests, so pods need realistic CPU and memory requests. Combine it with the Horizontal Pod Autoscaler so the number of pods also follows the load.
