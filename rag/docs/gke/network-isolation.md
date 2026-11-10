---
title: GKE network isolation: authorized networks and private nodes
service: gke
source_url: https://cloud.google.com/kubernetes-engine/docs/concepts/network-isolation
---

## Control plane access

The GKE control plane exposes the Kubernetes API. By default it has an external endpoint reachable from any IP address, protected only by authentication. Authorized networks limit that endpoint to CIDR ranges you list, such as an office or VPN range. The external endpoint can also be disabled so the control plane is reached only over internal addresses.

## Private nodes

With private nodes enabled, nodes have only internal IP addresses and cannot be reached from the internet. They pull images and reach external services through Cloud NAT and Private Google Access. Private nodes together with authorized networks are the recommended baseline for production clusters, because they remove direct internet exposure of both the nodes and the API server.
