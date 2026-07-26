# terraform-module-resource

Golden path for a **single-resource** Terraform module (`tfm-*` repository naming).
Use when a team needs one governed scaffold file (for example `aws_s3_bucket`) instead
of the multi-service scope flow in `terraform-module-generic`.

Inputs: `provider_service` + `provider_resource` (validated against
`provider-catalog.json`, symlinked from the generic blueprint).
