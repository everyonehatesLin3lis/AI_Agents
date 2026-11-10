---
title: Cloud SQL high availability
service: cloud_sql
source_url: https://cloud.google.com/sql/docs/mysql/high-availability
---

## How it works

A high availability (regional) Cloud SQL instance has a primary and a standby in two zones of the same region. Data is written synchronously to both zones, and Cloud SQL fails over to the standby automatically when the primary instance or its zone fails. It is selected with availability_type = REGIONAL.

## Cost

The standby is billed like a second instance, so the compute and storage price of an HA instance is about twice that of a zonal instance with the same shape. HA is appropriate for production databases with an availability target. Development, test and staging databases usually do not need it, and switching them to ZONAL roughly halves their cost. The standby cannot serve read traffic: use read replicas for that.
