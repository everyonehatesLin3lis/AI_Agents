---
title: What is Cloud Run
service: cloud_run
source_url: https://cloud.google.com/run/docs/overview/what-is-cloud-run
---

## What it is

Cloud Run is a managed platform that runs containers without any servers or clusters to manage. A service gets an HTTPS endpoint, scales automatically with traffic, including down to zero, and is billed for the resources used while handling requests. Cloud Run jobs run containers to completion for batch work.

## When it is the simpler choice

A stateless HTTP application or API in a container usually runs on Cloud Run with far less to operate than a VM or a Kubernetes cluster: no operating system patching, no node pools and no cluster fee. Kubernetes Engine is the better fit when the workload needs Kubernetes APIs, custom networking, stateful sets or daemon sets. A small web service on a dedicated VM or a small GKE cluster is often a candidate for moving to Cloud Run.
