---
title: VPC firewall rules
service: compute
source_url: https://cloud.google.com/firewall/docs/firewalls
---

## How rules work

VPC firewall rules allow or deny connections to and from VM instances. Each rule has a direction, a priority, an action, a target, a source or destination, and protocols and ports. Rules are stateful. Every network has an implied rule that denies all ingress and an implied rule that allows all egress.

## Good practice

Follow least privilege: allow only the ports a workload needs, from the narrowest source ranges. Use target tags or target service accounts so a rule applies to specific VMs and not the whole network. Database ports such as 3306 and 5432 should be reachable only from the application tier, never from 0.0.0.0/0. Enable firewall rule logging when you need to audit what a rule allows.
