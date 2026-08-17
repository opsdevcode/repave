# terraform-component-bucket

Golden path for a **managed object bucket** GitOps stack (`components/bucket/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_s3-stub` module with `aws_s3_bucket`, `azurerm_storage_account`, or
`google_storage_bucket`. Pin your estate `tf-*` module before shared apply.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
