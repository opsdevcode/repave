variable "environment" {
  type = string
}

variable "tags" {
  type = map(string)
}

variable "api_token" {
  type    = string
  default = "AKIAIOSFODNN7EXAMPLE"
}
