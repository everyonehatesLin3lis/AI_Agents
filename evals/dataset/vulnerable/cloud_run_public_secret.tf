# A public Cloud Run service with a database password in a plain environment variable.
resource "google_cloud_run_v2_service" "api" {
  name     = "orders-api"
  location = "us-central1"

  template {
    scaling {
      min_instance_count = 2
      max_instance_count = 10
    }

    containers {
      image = "us-docker.pkg.dev/acme/app/api:1.0"

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }

      env {
        name  = "DB_PASSWORD"
        value = "hunter2-prod"
      }

      env {
        name  = "LOG_LEVEL"
        value = "info"
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = "us-central1"
  role     = "roles/run.invoker"
  member   = "allUsers"
}
