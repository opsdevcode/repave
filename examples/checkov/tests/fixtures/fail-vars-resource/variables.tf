variable "environment" {
  type = string
}

variable "tags" {
  type = map(string)
}

resource "null_resource" "bad" {}
