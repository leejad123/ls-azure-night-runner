#!/usr/bin/env bash
set -euo pipefail

# Azure bootstrap helper for ls-azure-night-runner.
#
# Requirements:
#   - Run from the ls-azure-night-runner repo root.
#   - Docker CLI installed and daemon running.
#   - Azure CLI installed and authenticated (run `az login` beforehand).
#   - LS_SPEC_ROOT must be provided at runtime (mount or clone ls-spec inside the job).

RESOURCE_GROUP="${RESOURCE_GROUP:-ls-night-runner-rg}"
LOCATION="${LOCATION:-canadacentral}"
ACR_NAME="${ACR_NAME:-youracrname}"  # TODO: set to your unique ACR name
ENV_NAME="${ENV_NAME:-ls-night-runner-env}"
JOB_NAME="${JOB_NAME:-ls-night-runner-job}"
IMAGE_TAG="${IMAGE_TAG:-ls-azure-night-runner:dev}"

FULL_IMAGE="$ACR_NAME.azurecr.io/$IMAGE_TAG"

echo "[Night Runner] Building local image $IMAGE_TAG..."
docker build -t "$IMAGE_TAG" .

echo "[Night Runner] Ensuring resource group $RESOURCE_GROUP exists in $LOCATION..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

echo "[Night Runner] Creating ACR $ACR_NAME if missing..."
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --only-show-errors || true

echo "[Night Runner] Logging into ACR $ACR_NAME..."
az acr login --name "$ACR_NAME"

echo "[Night Runner] Tagging and pushing $FULL_IMAGE..."
docker tag "$IMAGE_TAG" "$FULL_IMAGE"
docker push "$FULL_IMAGE"

echo "[Night Runner] Creating Container Apps environment $ENV_NAME if needed..."
az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --only-show-errors || true

echo "[Night Runner] Creating or updating Container App Job $JOB_NAME..."
az containerapp job create \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image "$FULL_IMAGE" \
  --trigger-type Schedule \
  --cron-expression "0 4 * * *" \
  --cpu "0.25" \
  --memory "0.5Gi" \
  --env-vars LS_SPEC_ROOT=/workspace/ls-spec \
  --registry-server "$ACR_NAME.azurecr.io" \
  --only-show-errors || \
az containerapp job update \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$FULL_IMAGE" \
  --env-vars LS_SPEC_ROOT=/workspace/ls-spec \
  --only-show-errors

echo ""
echo "Bootstrap complete. Summary:"
echo "  Resource Group : $RESOURCE_GROUP"
echo "  Location       : $LOCATION"
echo "  ACR Name       : $ACR_NAME"
echo "  Environment    : $ENV_NAME"
echo "  Job Name       : $JOB_NAME"
echo "  Image Tag      : $FULL_IMAGE"
echo "Run 'chmod +x scripts/azure_bootstrap.sh' before executing this script."
