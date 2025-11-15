# Azure Deployment Runbook — ls-azure-night-runner

## 1. Purpose
This document describes how to deploy the ls-azure-night-runner orchestrator image into Azure using Azure Container Registry (ACR) and Azure Container Apps Jobs. Spec and Doctrine remain in ls-spec, missions live under `ops/night_missions`, and this image executes Night Plans inside Azure. GitHub remains the merge gate and ledger.

## 2. Prerequisites
- Docker installed and running.
- `az` CLI installed and logged in (`az login`).
- Local workspace layout:
```
workspace/
  ls-spec/
  ls-azure-night-runner/
```
- A GitHub token or GitHub App available later for read-only or PR access.

## 3. Build and tag Docker image

Build:
```
docker build -t ls-azure-night-runner:dev .
```

Tag for ACR (replace `ACR_NAME` and `IMAGE_TAG`):
```
ACR_NAME=youracrname
IMAGE_TAG=ls-azure-night-runner:dev

az acr login --name "$ACR_NAME"
docker tag ls-azure-night-runner:dev "$ACR_NAME.azurecr.io/$IMAGE_TAG"
docker push "$ACR_NAME.azurecr.io/$IMAGE_TAG"
```

## 4. Create Azure resources

Example resource group and ACR creation:
```
RESOURCE_GROUP=ls-night-runner-rg
ACR_NAME=youracrname

az group create --name "$RESOURCE_GROUP" --location canadacentral
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic
```

## 5. Deploy as Azure Container App Job

Create container apps environment:
```
ENV_NAME=ls-night-runner-env

az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location canadacentral
```

Create job (nightly schedule):
```
JOB_NAME=ls-night-runner-job

az containerapp job create \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --image "$ACR_NAME.azurecr.io/$IMAGE_TAG" \
  --trigger-type Schedule \
  --cron-expression "0 4 * * *" \
  --cpu "0.25" \
  --memory "0.5Gi" \
  --env-vars LS_SPEC_ROOT=/workspace/ls-spec \
  --registry-server "$ACR_NAME.azurecr.io"
```

## 6. Providing ls-spec to the container

The orchestrator expects `LS_SPEC_ROOT=/workspace/ls-spec`. Options:
- Mount an Azure Files share containing a checkout of `ls-spec` at that path.
- Or clone `ls-spec` inside the container at startup using a read-only GitHub token.

## 7. GitHub access (future work)

Full Night Runner behavior in Azure will require:
- A GitHub App or PAT stored in Azure Key Vault or as a secret.
- Read access to `ls-spec`, `ls-devops`, `ls-backend`, `ls-scheduler`.
- Write access to sandbox branches.
- Permission to open PRs.

## 8. Observability (future work)

Azure Monitor or Log Analytics can ingest:
- Night Runner logs,
- Result JSON files,
- Proof Chain entries,
- Dashboards for mission attempts, failures, throughput, and repo coverage.
