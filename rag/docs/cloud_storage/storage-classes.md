---
title: Storage classes
service: cloud_storage
source_url: https://cloud.google.com/storage/docs/storage-classes
---

## The four classes

Cloud Storage offers Standard, Nearline, Coldline and Archive storage. Standard has the highest storage price and no retrieval fee, and suits frequently accessed data. Nearline is cheaper to store and suits data read about once a month or less. Coldline suits data read about once a quarter. Archive is the cheapest to store and suits data read less than once a year.

## Trade-offs to check before switching

The colder classes charge a retrieval fee per GB read and have a minimum storage duration: 30 days for Nearline, 90 days for Coldline and 365 days for Archive. Deleting or rewriting an object earlier is billed as if it had been stored for the full minimum. Choosing a colder class for data that is read often can cost more than Standard. All classes have the same low latency and durability.
