# Module repositories

Generated modules **never** live inside the repave monorepo. Each golden path
produces an independent git repository under your configured modules root.

## Configuration

Copy and edit the example config:

```bash
cp repave.config.yaml.example repave.config.yaml
# output.github_org, output.modules_root
```

Or environment variables:

```bash
export REPAVE_GITHUB_ORG=your-org
export REPAVE_MODULES_ROOT=$HOME/repave-modules
export GITHUB_TOKEN=ghp_...   # repo scope; required for remote publish
```

## Layout and GitHub naming

Terraform modules typically land at:

```text
$(modules_root)/tf-<cloud_provider>-<module_name>/
```

Remote URL shape:

```text
https://github.com/<org>/tf-<cloud_provider>-<module_name>
```

GitOps delivery manifests land at one repository per service per environment:

```text
$(modules_root)/gitops-<environment>-<service_name>/
```

Ansible and other artifact types follow blueprint-specific naming in
[`blueprints/`](../blueprints/).

## Remote publish

When dry-run is disabled and `GITHUB_TOKEN` is set, repave creates the target
repository if needed and pushes the initial commit to `main`. See
[Concepts — remote publish](concepts.md#remote-publish).
