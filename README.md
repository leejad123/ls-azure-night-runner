# ls-azure-night-runner

Azure-hosted Night Runner orchestrator for Living Shield.

This repo implements the target architecture described in [ls-spec/ops/AZURE_NIGHT_RUNNER_ARCH.md](../ls-spec/ops/AZURE_NIGHT_RUNNER_ARCH.md): Spec and Doctrine remain in `ls-spec`, Night Missions follow the NM-XXX schema, Azure containers provide the execution fabric, and GitHub acts as the merge gate plus public ledger.

- See [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md) for container build and Azure deployment steps.

- For a scripted bootstrap of ACR plus the Container App Job, see [`scripts/azure_bootstrap.sh`](scripts/azure_bootstrap.sh).
