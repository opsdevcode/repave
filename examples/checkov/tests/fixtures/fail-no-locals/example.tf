resource "null_resource" "example" {
  triggers = {
    name_prefix = "bad"
    tags        = jsonencode({})
  }
}
