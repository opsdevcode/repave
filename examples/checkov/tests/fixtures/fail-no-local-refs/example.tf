resource "null_resource" "example" {
  triggers = {
    name_prefix = var.environment
    tags        = jsonencode(var.tags)
  }
}
