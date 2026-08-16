variable "stack_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "name_prefix" {
  type    = string
  default = ""
}

variable "tags" {
  type = map(string)
}

# Stand-in for a managed object bucket (S3 / GCS / Blob). Replace this module
# source with your estate tf-* coordinates before applying via CD.
resource "null_resource" "example" {
  triggers = {
    stack       = var.stack_name
    environment = var.environment
    prefix      = var.name_prefix
    tags        = jsonencode(var.tags)
  }
}

output "resource_ids" {
  value = [null_resource.example.id]
}
