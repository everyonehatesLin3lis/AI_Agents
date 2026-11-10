---
title: Cloud SQL backups
service: cloud_sql
source_url: https://cloud.google.com/sql/docs/mysql/backup-recovery/backups
---

## Automated backups

Cloud SQL can take an automated backup every day in a backup window you choose, and keeps a configurable number of them. Backups are incremental and are needed to restore an instance after data loss or corruption. On-demand backups can be taken at any time, for example before a risky change.

## Point-in-time recovery and cost

Point-in-time recovery uses binary or write-ahead logs to restore an instance to a specific moment, and requires automated backups to be enabled. Backup storage is billed per GB. An instance without backups cannot be recovered after an accidental delete or a bad migration, so backups should be enabled for anything that holds real data.
