---
title: Cloud SQL deletion protection
service: cloud_sql
source_url: https://cloud.google.com/sql/docs/mysql/deletion-protection
---

## What it does

Deletion protection blocks an instance from being deleted until the setting is turned off. It guards against deleting a database by mistake, for example through a wrong terraform destroy or a mistyped command.

## Recommendation

Enable deletion protection on every instance that holds data you cannot recreate. It can be disabled deliberately when the instance really has to be removed, so it costs nothing and only adds a confirmation step.
