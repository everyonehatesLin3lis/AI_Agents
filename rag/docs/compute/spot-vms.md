---
title: Spot VMs
service: compute
source_url: https://cloud.google.com/compute/docs/instances/spot
---

## What they are

Spot VMs use spare Compute Engine capacity at a much lower price than standard VMs, with discounts that can be very large. In exchange, Compute Engine can stop (preempt) them at any time with short notice, and they have no availability guarantee. Spot VMs replace the older preemptible VMs and have no maximum runtime.

## Good and bad fits

Spot VMs suit fault-tolerant work: batch jobs, CI runners, data processing, stateless workers behind a queue and development environments. They are a poor fit for a single VM that serves users, or for databases, because the VM can disappear at any moment. Managed instance groups can recreate preempted Spot VMs automatically when capacity returns.
