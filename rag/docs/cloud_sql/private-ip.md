---
title: Private IP for Cloud SQL
service: cloud_sql
source_url: https://cloud.google.com/sql/docs/mysql/private-ip
---

## How private IP works

With private IP, a Cloud SQL instance gets an internal address in your VPC network through private services access, and is not reachable from the public internet. Applications in the same VPC, or connected networks, reach the database over internal addresses. Setting ipv4_enabled to false removes the public address.

## Why prefer it

A private instance has a smaller attack surface, needs no authorized networks, and its traffic stays on Google's network, which also lowers latency. Private IP requires a VPC network with an allocated IP range and a private services access connection. Serverless products such as Cloud Run reach a private instance through Direct VPC egress or a Serverless VPC Access connector.
