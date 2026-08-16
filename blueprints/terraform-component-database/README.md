# terraform-component-database

Golden path for a **managed database** GitOps stack (`components/database/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_rds-stub` module with a real `aws_db_instance` (Azure/GCP keep a placeholder).
Pin your estate `tf-*` module before shared apply.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
