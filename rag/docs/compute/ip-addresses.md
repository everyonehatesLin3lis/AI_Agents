---
title: IP addresses for VMs
service: compute
source_url: https://cloud.google.com/compute/docs/ip-addresses
---

## External and internal addresses

A VM always has an internal IP address and can also have an external one. A VM with an external address can be reached directly from the internet, limited only by firewall rules. A VM without one can still reach Google APIs through Private Google Access, and the internet through Cloud NAT.

## Recommendation and cost

Most VMs do not need an external address. Serve user traffic through a load balancer, reach machines for administration through IAP, and send outbound traffic through Cloud NAT. External IPv4 addresses are billed, including static addresses that are reserved but not attached, so removing unneeded addresses reduces both exposure and cost.
