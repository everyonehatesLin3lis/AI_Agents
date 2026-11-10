---
title: Object Versioning
service: cloud_storage
source_url: https://cloud.google.com/storage/docs/object-versioning
---

## What it does

Object Versioning keeps a noncurrent version of an object each time the live version is replaced or deleted. Noncurrent versions can be listed and restored, which protects against accidental overwrites and deletions.

## Cost and lifecycle

Each noncurrent version is billed like a live object, so versioning increases storage cost when objects change often. Combine versioning with an Object Lifecycle Management rule that deletes noncurrent versions after a number of days or keeps only the newest few versions. Soft delete is a separate feature that keeps deleted objects for a retention period.
