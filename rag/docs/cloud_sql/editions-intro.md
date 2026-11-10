---
title: Cloud SQL editions and machine sizing
service: cloud_sql
source_url: https://cloud.google.com/sql/docs/mysql/editions-intro
---

## Editions

Cloud SQL has two editions. Enterprise covers general workloads. Enterprise Plus adds higher performance machine types, a data cache, near-zero downtime maintenance and a higher availability SLA, at a higher price. Choose the edition by the availability and performance the workload actually needs.

## Sizing

Instance price is driven by vCPUs, memory and storage. Shared-core tiers such as db-f1-micro and db-g1-small are cheap but are meant for development and testing and are not covered by the SLA. For production, pick a dedicated-core shape close to observed usage: an oversized instance is the most common source of Cloud SQL overspend. Committed use discounts are available for steady workloads.
