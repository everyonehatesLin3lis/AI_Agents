---
title: IAP TCP forwarding for SSH and RDP
service: compute
source_url: https://cloud.google.com/iap/docs/using-tcp-forwarding
---

## What it does

Identity-Aware Proxy (IAP) TCP forwarding lets administrators reach SSH, RDP and other TCP ports on VMs that have no public IP address. The connection is wrapped in HTTPS and is allowed only after IAM checks that the user has the IAP-secured Tunnel User role.

## Firewall rule to use

Instead of allowing port 22 or 3389 from 0.0.0.0/0, allow them only from the IAP range 35.235.240.0/20. SSH and RDP ports open to the internet are scanned constantly and are a common way into a project. With IAP, access is tied to a Google identity and is logged, and the VM does not need an external address at all.
