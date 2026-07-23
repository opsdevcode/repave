# Generic Terraform Module Standard (sample)

Version: 0.2.0

This is a **sample** standards document for the repave bring-your-own-standards
model. In real deployments, point blueprints at your authoritative standards
source in git and pin the version they encode.

## Module contract

- Pin Terraform and provider versions in `versions.tf`.
- Declare typed variables with descriptions and safe defaults where appropriate.
- Expose explicit outputs for module contract behavior.
- Place shared module locals in `locals.tf`.
- Put each in-scope provider resource in its own `.tf` file (for example `s3_bucket.tf`,
  `eks_cluster.tf`) instead of a monolithic `main.tf`.
- Include native Terraform tests under `tests/` using `.tftest.hcl`.
- Include a module README with purpose, usage, inputs, outputs, and upgrade notes.

## Required CI gates

- `terraform fmt -check -recursive`
- `terraform validate`
- `terraform test`
- `tflint`
- `checkov` (or equivalent policy scanner)
- Docs drift check (README must be present and fully rendered)
