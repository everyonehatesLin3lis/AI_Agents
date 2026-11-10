# SSH and database ports open to the world, on a VM with a public IP and full API access.
resource "google_compute_firewall" "allow_ssh" {
  name    = "allow-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
}

resource "google_compute_firewall" "allow_db" {
  name    = "allow-db"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["5432", "3306"]
  }

  source_ranges = ["0.0.0.0/0"]
}

resource "google_compute_instance" "web" {
  name         = "web-1"
  machine_type = "n2-standard-4"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 50
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  service_account {
    scopes = ["cloud-platform"]
  }
}
