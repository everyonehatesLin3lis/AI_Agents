---
title: Cloud Run billing settings
service: cloud_run
source_url: https://cloud.google.com/run/docs/configuring/billing-settings
---

## Two billing modes

With request-based billing, the default, CPU is allocated and billed only while an instance is processing requests, and there is a per-request fee. With instance-based billing, CPU is always allocated for the whole life of each instance, there is no per-request fee, and the per-second rates for CPU and memory are lower.

## Which to choose

Request-based billing is cheaper for services with low or uneven traffic. Instance-based billing can be cheaper for services with steady, high traffic, and is required for work that continues after the response is sent, such as background tasks. Combining instance-based billing with minimum instances means paying the full rate around the clock, so check that the workload really needs it.
