# A small web stack: mostly fine, with two gaps and one resource type we do not review.
resource "google_compute_firewall" "web" {
  name    = "allow-web"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
}

resource "google_compute_instance" "app" {
  count        = 2
  name         = "app-${count.index}"
  machine_type = "e2-standard-2"
  zone         = "europe-west1-b"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"
  }
}

resource "google_sql_database_instance" "db" {
  name             = "app-db"
  database_version = "MYSQL_8_0"
  region           = "europe-west1"

  settings {
    tier = "db-f1-micro"

    ip_configuration {
      ipv4_enabled    = false
      private_network = "projects/acme/global/networks/default"
      ssl_mode        = "ENCRYPTED_ONLY"
    }
  }
}

resource "google_storage_bucket" "uploads" {
  name                        = "acme-user-uploads"
  location                    = "EU"
  storage_class               = "COLDLINE"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

resource "google_pubsub_topic" "events" {
  name = "app-events"
}
