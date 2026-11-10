---
title: Authorize with authorized networks
service: cloud_sql
source_url: https://cloud.google.com/sql/docs/mysql/authorize-networks
---

## What authorized networks are

A Cloud SQL instance with a public IP address accepts connections only from the IP ranges listed as authorized networks. Each entry is a CIDR range. The range 0.0.0.0/0 allows every IPv4 address on the internet to reach the database port, which leaves only the database password between an attacker and the data.

## Safer ways to connect

Use the narrowest ranges possible, and never 0.0.0.0/0. Better options are private IP, or the Cloud SQL Auth Proxy and the Cloud SQL language connectors, which authenticate with IAM, encrypt the connection and do not need any authorized network entry.
