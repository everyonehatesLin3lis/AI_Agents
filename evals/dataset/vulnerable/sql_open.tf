# A production database reachable from any IP address, without TLS or backups.
resource "google_sql_database_instance" "main" {
  name                = "orders-db"
  database_version    = "POSTGRES_15"
  region              = "us-central1"
  deletion_protection = false

  settings {
    tier              = "db-custom-2-7680"
    availability_type = "REGIONAL"
    disk_size         = 100
    disk_type         = "PD_SSD"

    ip_configuration {
      ipv4_enabled = true

      authorized_networks {
        name  = "everyone"
        value = "0.0.0.0/0"
      }
    }
  }
}
