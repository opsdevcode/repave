# Legacy placeholder module body (operator e2e fixture).

resource "null_resource" "example" {
  triggers = {
    placeholder = "terraform-minimal-fixture"
  }
}

output "resource_ids" {
  value = [null_resource.example.id]
}
