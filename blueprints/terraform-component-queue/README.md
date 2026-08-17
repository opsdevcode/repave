# terraform-component-queue

Golden path for a **managed queue** GitOps stack (`components/queue/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_sqs-stub` module with `aws_sqs_queue`, `azurerm_servicebus_queue`, or
`google_pubsub_topic`. Pin your estate `tf-*` module before shared apply.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
