variable "module_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "owner" {
  type    = string
  default = "platform"
}

variable "service" {
  type    = string
  default = "example"
}

variable "cost_center" {
  type    = string
  default = ""
}

variable "tags" {
  type = map(string)
}
