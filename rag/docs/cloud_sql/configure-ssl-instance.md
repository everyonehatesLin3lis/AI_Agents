---
title: Configure SSL/TLS for Cloud SQL
service: cloud_sql
source_url: https://cloud.google.com/sql/docs/mysql/configure-ssl-instance
---

## SSL modes

Cloud SQL can accept both unencrypted and encrypted connections, or enforce encryption. The ssl_mode setting has three values: ALLOW_UNENCRYPTED_AND_ENCRYPTED, ENCRYPTED_ONLY, and TRUSTED_CLIENT_CERTIFICATE_REQUIRED, which also requires a valid client certificate.

## Recommendation

Set the SSL mode to ENCRYPTED_ONLY or stricter so that credentials and data are never sent in clear text. This matters most for instances with a public IP address. Connections made through the Cloud SQL Auth Proxy or the language connectors are always encrypted.
