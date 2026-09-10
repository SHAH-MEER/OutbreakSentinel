"""Lambda entrypoint for the API, wrapping the FastAPI app with Mangum for
API Gateway (HTTP API) integration. See infra/api.tf."""
from mangum import Mangum

from api.main import app

handler = Mangum(app)
