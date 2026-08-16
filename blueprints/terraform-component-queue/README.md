# terraform-component-queue

Golden path for a **managed queue** GitOps stack (`components/queue/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_sqs-stub` module with a real `aws_sqs_queue` (Azure/GCP keep a placeholder).
Pin your estate `tf-*` module before shared apply.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
