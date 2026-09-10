# Remote state — required before infra/deploy.yml's CD workflow can run
# terraform apply safely. Every CI run starts from a fresh checkout with
# no local .tfstate; without a remote backend, each run would think
# nothing exists yet and either fail on "already exists" for uniquely
# named resources or (worse) create duplicates of everything else.
#
# Deliberately a PARTIAL backend config (no bucket/region/table here) —
# those are account-specific and passed via -backend-config flags at
# init time instead of hardcoded into version control. See the one-time
# bootstrap steps in infra/README.md.
terraform {
  backend "s3" {}
}
