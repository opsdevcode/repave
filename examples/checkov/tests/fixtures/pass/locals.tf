locals {
  name_prefix = "${var.module_name}-${var.environment}"
  common_tags = merge(var.tags, { managed_by = "terraform" })
}
