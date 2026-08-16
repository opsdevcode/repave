# terraform-component-bucket

Golden path for a **managed object bucket** GitOps stack (`components/bucket/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_s3-stub` module so gates pass. Replace the source with your S3 / GCS / Blob
`tf-*` module before merge.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
