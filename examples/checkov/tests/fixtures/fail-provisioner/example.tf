resource "null_resource" "example" {
  provisioner "local-exec" {
    command = "echo hello"
  }

  triggers = {
    name_prefix = local.name_prefix
    tags        = jsonencode(local.common_tags)
  }
}
