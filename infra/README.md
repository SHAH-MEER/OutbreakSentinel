# Infrastructure (Terraform)

Implements the AWS pipeline from the project brief:

```text
EventBridge (weekly cron)
  -> Step Functions: Ingest Lambda -> Process Lambda -> Map(Detect Lambda x detect_shard_count)
       Ingest:  pulls latest CDC NNDSS data -> S3 raw zone
       Process: raw JSON -> tidy weekly panel -> S3 processed zone
       Detect:  STL-residual detection over this shard's series -> DynamoDB alerts
                (fanned out across detect_shard_count parallel invocations —
                see the note on detect_shard_count below for why)
  -> CloudWatch alarms on Step Functions / Lambda failures
```

All three pipeline Lambdas share one container image (different
`image_config.command` per function) because they need pandas, numpy,
statsmodels, and ruptures — well over the ~250MB unzipped limit for a
plain zip-based Lambda package. (`ruptures` is a dependency of
`detection/changepoint.py`, the documented alternative method — see
detection/README.md — not the one that ships in `run_detection.py`; it's
still in the shared image so the Detect Lambda's dependencies match what
gets tested and could be swapped back in without a rebuild.)

**Why Detect is sharded, not one invocation**: scoring every series in
the panel (~10.2k, after fixing a region-name casing bug that had been
silently splitting most states' history in two — see data/README.md)
with STL seasonal decomposition was benchmarked at ~884s serially — over
half of the 900s hard cap on its own, before any of the usual production
margin (real Lambda vCPUs are typically slower per-core than a dev
machine; cold starts add more). The Step Functions Map state
(`infra/step_functions.tf`) instead fans out `detect_shard_count`
(default 10) parallel invocations, each scoring a disjoint ~1/10th of the
panel via a stable hash partition (`detection/run_detection.series_shard`)
— each one comfortably under the timeout with real margin, rather than
one invocation running close to the edge.

## What this does NOT include yet

- **API + dashboard** (Phase 4): API Gateway, the FastAPI/Mangum Lambda,
  and the Streamlit/App Runner dashboard aren't provisioned here. This
  stack only covers ingestion through writing alerts to DynamoDB.
- **Remote Terraform state**: this uses local state. Fine for a solo
  portfolio project; add an S3 backend + DynamoDB lock table before
  anyone else touches this.

## Cost note

Everything here is pay-per-use (Lambda, Step Functions, DynamoDB
on-demand, S3, ECR, one weekly EventBridge trigger) — there is no
always-on compute. At NNDSS's data volumes this should run a few dollars
a month at most, dominated by nothing in particular; the free tier likely
covers most of it. There is no cost while `terraform apply` hasn't been
run — writing/reviewing this code creates nothing.

## Deploying (two-step, because of a real bootstrapping order problem)

`aws_lambda_function` with `package_type = "Image"` requires the image to
already exist in ECR at apply time — but the ECR repo itself is also
defined in this same Terraform config. So the first apply can only create
the repo; the image has to be built and pushed before Terraform can
create the Lambda functions that reference it.

**This creates real, billable AWS resources. Requires AWS credentials
configured (`aws configure` / `AWS_PROFILE`) and should be reviewed
(`terraform plan`) before every apply — don't run `apply` without reading
the plan first.**

```bash
cd infra
terraform init
terraform apply -target=aws_ecr_repository.pipeline   # step 1: repo only

# step 2: build and push the image the Lambdas will reference
aws ecr get-login-password --region <region> \
  | docker login --username AWS --password-stdin <account_id>.dkr.ecr.<region>.amazonaws.com
docker build -f docker/Dockerfile -t outbreak-sentinel-pipeline ..   # context = repo root
docker tag outbreak-sentinel-pipeline:latest <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest

terraform apply   # step 3: everything else
```

To tear down: `terraform destroy` (this repo's `force_delete` on the ECR
repo means destroy won't get blocked by leftover images).

## Redeploying a code change

Rebuild and push a new image tag, then `terraform apply` again with
`-var lambda_image_tag=<new-tag>` (or just re-push `:latest` and force a
Lambda update — Terraform won't detect an in-place image content change
under the same tag on its own, so either bump the tag or run
`aws lambda update-function-code` directly after pushing).
