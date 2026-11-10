resource "google_storage_bucket" "reports" {
  name                        = "acme-monthly-reports"
  location                    = "europe-west1"
  storage_class               = "NEARLINE"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket_iam_member" "analysts" {
  bucket = google_storage_bucket.reports.name
  role   = "roles/storage.objectViewer"
  member = "group:analysts@example.com"
}
