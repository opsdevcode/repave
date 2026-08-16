# terraform-component-queue

Golden path for a **managed queue** GitOps stack (`components/queue/{name}`).
Same composition shape as `terraform-environment-stack`; the default pin is an
`_sqs-stub` module so gates pass. Replace the source with your SQS / Pub/Sub
`tf-*` module before merge.

Standard: `standards/terraform-environment-stack-standard.md` @ 0.1.0.
