---
title: Autoclass
service: cloud_storage
source_url: https://cloud.google.com/storage/docs/autoclass
---

## What it does

Autoclass moves each object between storage classes automatically, based on how that object is accessed. Objects that are not read move to colder classes over time, and an object that is read again moves back to Standard. It is enabled per bucket.

## When to choose it over lifecycle rules

Autoclass fits buckets where the access pattern is unknown or mixed, because it needs no rules and has no retrieval fees or early deletion charges for the transitions it makes. It adds a management fee per object, so it is less attractive for buckets with a very large number of small objects. When the access pattern is predictable, explicit lifecycle rules are usually cheaper.
