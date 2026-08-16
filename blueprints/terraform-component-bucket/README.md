# terraform-component-bucket

Golden path for a **managed object bucket** GitOps stack (`components/bucket/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_s3-stub` module with a real `aws_s3_bucket` (Azure/GCP keep a placeholder).
Pin your estate `tf-*` module before shared apply.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
