# terraform-component-database

Golden path for a **managed database** GitOps stack (`components/database/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_rds-stub` module so gates pass. Replace the source with your RDS / Cloud SQL
`tf-*` module before merge.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
