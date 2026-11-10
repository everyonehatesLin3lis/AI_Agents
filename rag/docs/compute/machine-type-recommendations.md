---
title: Machine type (rightsizing) recommendations
service: compute
source_url: https://cloud.google.com/compute/docs/instances/apply-machine-type-recommendations-for-instances
---

## What they are

Compute Engine analyses the CPU and memory usage of each VM and recommends a machine type that fits it better. A VM that uses little of its capacity gets a recommendation for a smaller type with an estimated saving. A VM that runs hot gets a recommendation for a larger type.

## How to act on them

Rightsizing is often the largest and safest saving, because many VMs are sized by guesswork. Before the infrastructure exists, choose a modest machine type and scale up after measuring. Custom machine types let you set vCPUs and memory separately when no predefined shape fits. Changing a machine type requires stopping the VM.
