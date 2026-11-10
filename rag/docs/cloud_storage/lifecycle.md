---
title: Object Lifecycle Management
service: cloud_storage
source_url: https://cloud.google.com/storage/docs/lifecycle
---

## What it does

Object Lifecycle Management applies rules to the objects in a bucket automatically. A rule has a condition, such as object age, number of newer versions or creation date, and an action, such as Delete or SetStorageClass. Typical rules move objects to Nearline or Coldline after 30 or 90 days, or delete temporary files and old noncurrent versions.

## Why it saves money

Without lifecycle rules, data that nobody reads stays in Standard storage forever. Moving old objects to a colder class or deleting them lowers the monthly storage bill without any application change. Rules are evaluated asynchronously, so an action can take up to a day to apply after an object meets the condition.
