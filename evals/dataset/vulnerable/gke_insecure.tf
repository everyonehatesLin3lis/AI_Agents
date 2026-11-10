# A regional GKE cluster with a public control plane, public nodes and legacy settings.
resource "google_container_cluster" "primary" {
  name               = "prod"
  location           = "us-central1"
  enable_legacy_abac = true
  initial_node_count = 1

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-balanced"
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}
