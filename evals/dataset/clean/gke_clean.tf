resource "google_container_cluster" "primary" {
  name                     = "prod"
  location                 = "us-central1-a"
  remove_default_node_pool = true
  initial_node_count       = 1

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = "203.0.113.0/24"
      display_name = "office"
    }
  }

  workload_identity_config {
    workload_pool = "acme.svc.id.goog"
  }
}

resource "google_container_node_pool" "main" {
  name       = "main"
  cluster    = google_container_cluster.primary.name
  node_count = 2

  node_config {
    machine_type    = "e2-standard-2"
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}
