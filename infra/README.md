# Infrastructure (Terraform)

Implements the full AWS pipeline + serving layer from the project brief:

```text
EventBridge (weekly cron)
  -> Step Functions: Ingest Lambda -> Process Lambda -> Map(Detect Lambda x detect_shard_count)
       Ingest:  pulls latest CDC NNDSS data -> S3 raw zone
       Process: raw JSON -> tidy weekly panel -> S3 processed zone
       Detect:  STL-residual detection over this shard's series -> DynamoDB alerts
                (fanned out across detect_shard_count parallel invocations —
                see the note on detect_shard_count below for why)
  -> CloudWatch alarms on Step Functions / Lambda failures

API Gateway (HTTP API) -> API Lambda (FastAPI via Mangum, read-only)
  -> reads current alerts from DynamoDB, series history from S3 processed zone

App Runner (Streamlit dashboard) -> polls the API over HTTP only
  -> never talks to DynamoDB/S3 directly (see dashboard/app.py)
```

Two container images, not one:

- **`infra/docker/Dockerfile`** — shared by the ingest/process/detect
  Lambdas *and* the API Lambda (different `image_config.command` per
  function; see `infra/lambda.tf` and `infra/api.tf`). All four need
  pandas/numpy at minimum, well over the ~250MB unzipped limit for a
  plain zip-based Lambda package, so this uses a trimmed
  `infra/docker/requirements-lambda.txt` rather than the full
  `requirements.txt` (no streamlit/plotly/pytest bloat in a Lambda
  image). `ruptures` stays in it even though `changepoint.py` isn't the
  shipped detection method (see detection/README.md) — it's the
  documented alternative, and keeping it in the image means it could be
  swapped back in via `image_config.command` without a rebuild.
- **`dashboard/Dockerfile`** — the Streamlit dashboard, deployed to App
  Runner rather than Lambda because it's a long-running server (a
  persistent per-viewer WebSocket connection doesn't fit Lambda's
  request/response model the way the API does). Its own trimmed
  `dashboard/requirements.txt` (streamlit/plotly/requests only — no
  boto3/pandas, since the dashboard never talks to AWS directly).

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

**Why the API Lambda's IAM role is separate from the pipeline's**: it
only ever reads (`dynamodb:Scan`/`GetItem`, `s3:GetObject`/`ListBucket`)
— giving it the pipeline's write-capable role would violate least
privilege for no benefit.

## What this does NOT include yet

- **Remote Terraform state**: this uses local state. Fine for a solo
  portfolio project; add an S3 backend + DynamoDB lock table before
  anyone else touches this.
- **Auth on the API/dashboard**: both are public and read-only by design
  (a demo dashboard, not a system handling sensitive data) — see the CORS
  note in `api/main.py`. Add an API key or Cognito authorizer before this
  is anything other than a portfolio piece.

## Cost note

Lambda, Step Functions, DynamoDB on-demand, S3, ECR, and the weekly
EventBridge trigger are all pay-per-use — no always-on compute there.
**App Runner is the one exception**: it bills for provisioned compute
whenever the service is running, not per-request, so the dashboard has a
real always-on cost (order of $5-10/month at the smallest instance size)
for as long as the service exists — unlike everything else in this
stack, `terraform destroy`-ing it when not actively demoing it is worth
doing. There is no cost at all while `terraform apply` hasn't been run —
writing/reviewing this code creates nothing.

## Deploying (two-step per image, because of a real bootstrapping order problem)

`aws_lambda_function` with `package_type = "Image"` and
`aws_apprunner_service` both require their image to already exist in ECR
at apply time — but the ECR repos themselves are also defined in this
same Terraform config. So the first apply can only create the two ECR
repos; each image has to be built and pushed before Terraform can create
the things that reference it.

**This creates real, billable AWS resources — including the
always-on App Runner cost above. Requires AWS credentials configured
(`aws configure` / `AWS_PROFILE`) and should be reviewed
(`terraform plan`) before every apply — don't run `apply` without reading
the plan first.**

```bash
cd infra
terraform init
terraform apply -target=aws_ecr_repository.pipeline -target=aws_ecr_repository.dashboard   # step 1: repos only

# step 2: build and push both images
aws ecr get-login-password --region <region> \
  | docker login --username AWS --password-stdin <account_id>.dkr.ecr.<region>.amazonaws.com

docker build -f docker/Dockerfile -t outbreak-sentinel-pipeline ..   # context = repo root
docker tag outbreak-sentinel-pipeline:latest <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest

docker build -f ../dashboard/Dockerfile -t outbreak-sentinel-dashboard ..   # context = repo root
docker tag outbreak-sentinel-dashboard:latest <dashboard_ecr_repository_url>:latest
docker push <dashboard_ecr_repository_url>:latest

terraform apply   # step 3: everything else, including wiring API_BASE_URL into the dashboard
```

To tear down: `terraform destroy` (this repo's `force_delete` on both ECR
repos means destroy won't get blocked by leftover images).

## Redeploying a code change

Rebuild and push a new image tag, then `terraform apply` again with
`-var lambda_image_tag=<new-tag>` and/or `-var dashboard_image_tag=<new-tag>`
(or just re-push `:latest` and force an update directly —
`aws lambda update-function-code` for a Lambda, or start a new App Runner
deployment via the console/CLI — since Terraform won't detect an
in-place image content change under the same tag on its own).

## Local development (no AWS needed)

```bash
uvicorn api.main:app --reload --port 8010          # API — falls back to
                                                     # computing alerts from
                                                     # the local processed
                                                     # parquet if ALERTS_TABLE
                                                     # isn't set (see api/data.py)
API_BASE_URL=http://127.0.0.1:8010 streamlit run dashboard/app.py
```
