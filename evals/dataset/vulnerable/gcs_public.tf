# A bucket that is readable by anyone on the internet.
resource "google_storage_bucket" "assets" {
  name          = "acme-public-assets"
  location      = "US"
  storage_class = "STANDARD"
}

resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.assets.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
