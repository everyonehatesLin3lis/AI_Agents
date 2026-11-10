---
title: Persistent Disk types
service: compute
source_url: https://cloud.google.com/compute/docs/disks
---

## The disk types

Persistent Disk has several types. Standard (pd-standard) uses hard disk drives, is the cheapest per GB, and suits sequential or rarely accessed data. Balanced (pd-balanced) uses SSD and balances price and performance for most workloads. SSD (pd-ssd) costs the most per GB and is meant for databases and other latency-sensitive workloads.

## Choosing for cost

You pay for provisioned size, not for used space, so oversized disks waste money every month. A boot disk for a stateless web or application server rarely needs pd-ssd: pd-balanced gives similar behaviour for much less. Keep pd-ssd for data disks that need high IOPS. Disks can be grown later without downtime, so start small.
