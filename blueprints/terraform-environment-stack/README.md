# terraform-environment-stack

Golden path for an **environment composition** repository (`env-*`) that wires one or
more **pinned** Terraform modules for a cloud provider and environment tier.

Bootstrap includes a local `modules/_example` stub so gates pass out of the box; replace
the module source with your `tf-*` / `tfm-*` module git or registry coordinates.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
