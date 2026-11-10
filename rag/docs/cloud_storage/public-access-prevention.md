---
title: Public access prevention
service: cloud_storage
source_url: https://cloud.google.com/storage/docs/public-access-prevention
---

## What it does

Public access prevention stops a Cloud Storage bucket from being exposed to the public internet. When it is enforced, IAM policies and ACLs that grant access to allUsers or allAuthenticatedUsers are blocked, and existing public grants stop working. It can be enforced on a single bucket or through an organization policy constraint for a whole project, folder or organization.

## When to use it

Enforce public access prevention on every bucket that is not meant to serve public content. A bucket that holds customer data, exports, backups or logs should never be readable by allUsers. If some objects must be shared, use signed URLs with a short expiry, or put public static content behind a load balancer and Cloud CDN instead of opening the bucket.
