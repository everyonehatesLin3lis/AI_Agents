---
title: Allowing public (unauthenticated) access
service: cloud_run
source_url: https://cloud.google.com/run/docs/authenticating/public
---

## How public access works

A Cloud Run service is private by default: every request must carry valid IAM credentials. Granting the Cloud Run Invoker role (roles/run.invoker) to allUsers makes the service public, so anyone on the internet can call it without authentication.

## When it is appropriate

Public access is correct for public websites and public APIs. It is wrong for internal services, webhooks that should verify their caller, admin tools and service-to-service backends. For those, grant the Invoker role only to the service accounts or users that need it, or restrict ingress to internal traffic and a load balancer. An organization policy for domain restricted sharing can block public access entirely.
