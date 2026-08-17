# terraform-component-database

Golden path for a **managed database** GitOps stack (`components/database/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_rds-stub` module with `aws_db_instance`, `azurerm_postgresql_flexible_server`,
or `google_sql_database_instance`. Pin your estate `tf-*` module before shared apply.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
