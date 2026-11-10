resource "google_cloud_run_v2_service" "api" {
  name     = "orders-api"
  location = "us-central1"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "us-docker.pkg.dev/acme/app/api:1.0"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name = "DB_PASSWORD"

        value_source {
          secret_key_ref {
            secret  = "db-password"
            version = "latest"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "frontend" {
  name     = google_cloud_run_v2_service.api.name
  location = "us-central1"
  role     = "roles/run.invoker"
  member   = "serviceAccount:frontend@acme.iam.gserviceaccount.com"
}
