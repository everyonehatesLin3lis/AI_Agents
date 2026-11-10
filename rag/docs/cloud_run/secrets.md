---
title: Configure secrets for Cloud Run services
service: cloud_run
source_url: https://cloud.google.com/run/docs/configuring/services/secrets
---

## The problem with plain environment variables

A password, token or API key written as a plain environment variable is stored in the service configuration and in the Terraform code and state, where everyone with read access to the project or repository can see it. It also cannot be rotated without a new deployment.

## Using Secret Manager

Store the value in Secret Manager and reference it from the service. Cloud Run can expose a secret as an environment variable or mount it as a file. The service's service account needs the Secret Manager Secret Accessor role on the secret. When a secret is exposed as an environment variable, pin it to a specific version so a revision always starts with a known value.
