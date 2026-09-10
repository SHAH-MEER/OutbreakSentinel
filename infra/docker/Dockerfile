# Build context must be the repo root (not this directory), since the
# ingest/process/detect Lambdas share this one image and need both
# data/ and detection/ from the top of the repo:
#
#   docker build -f infra/docker/Dockerfile -t outbreak-sentinel-pipeline .
#
# Which handler runs is chosen per-Lambda in Terraform via
# image_config.command (see infra/lambda.tf), not by this Dockerfile.
FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY data/ ${LAMBDA_TASK_ROOT}/data/
COPY detection/ ${LAMBDA_TASK_ROOT}/detection/
COPY infra/lambda_app/ ${LAMBDA_TASK_ROOT}/infra/lambda_app/

CMD ["infra.lambda_app.handlers.ingest_handler"]
