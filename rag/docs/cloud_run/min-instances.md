---
title: Minimum instances for Cloud Run
service: cloud_run
source_url: https://cloud.google.com/run/docs/configuring/min-instances
---

## What minimum instances do

By default Cloud Run scales to zero when a service receives no requests, and the next request waits for a cold start. Setting a minimum number of instances keeps that many instances warm so requests are served without that delay.

## Cost

Warm instances are billed even when they handle no traffic, at a lower idle rate when request-based billing is used. A service with minimum instances therefore has a fixed monthly cost, while a service that scales to zero costs nothing when idle. Use minimum instances only for latency-sensitive services, and keep the value at zero for internal tools, batch triggers and development environments.
