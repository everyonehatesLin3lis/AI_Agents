---
title: Uniform bucket-level access
service: cloud_storage
source_url: https://cloud.google.com/storage/docs/uniform-bucket-level-access
---

## What it does

Cloud Storage has two access systems: IAM, which applies to a whole bucket, and ACLs, which can be set per object. Uniform bucket-level access disables ACLs so that only IAM controls access. This makes permissions easier to audit, because one policy describes who can read every object in the bucket.

## Why it is recommended

With fine-grained ACLs a single object can be made public without anyone noticing in the bucket policy. Uniform bucket-level access removes that risk and is needed for features such as IAM Conditions and managed folders. Google recommends enabling it on new buckets. It can be switched back within a limited period, after which the setting becomes permanent.
