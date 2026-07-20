# Private Chat on AWS

Private Chat is a privacy-first personal chatbot starter built around an authenticated application tier, application-encrypted conversation storage and replaceable model backends. It supports a privacy-restricted OpenRouter adapter now and leaves a clean path to a privately networked GPU host later.

This repository implements the initial engineering foundation from the [project brief](Private-AWS-Chatbot-Project-Brief.docx). It is deliberately not presented as production-ready: authentication, durable AWS adapters and a reviewed deployment configuration must be completed before sensitive use.

![Private Chat interface concept](docs/design/chat-screen-concept.png)

## What is included

- A Python 3.12 FastAPI backend with Pydantic v2 validation.
- Ports-and-adapters boundaries for model inference, encrypted persistence, key management and GPU lifecycle control.
- An OpenRouter adapter that always supplies ZDR, denies provider data collection, disables fallbacks and requires an allowlist.
- A private self-hosted adapter for Ollama or vLLM-compatible endpoints.
- AES-256-GCM envelope-encryption primitives and safe in-memory development adapters.
- A React and TypeScript chat interface with accessible, responsive interactions.
- Terraform for private networking, KMS, encrypted conversation storage and an optional default-off GPU host.
- Provider-wide AWS cost tags for project, environment, owner, cost centre and repository reporting.
- Automated unit, contract, lint, type, build and Terraform checks.
- Architecture decisions, a threat model and operational runbooks.

## Architecture

```text
Browser
  |
  | HTTPS, authenticated
  v
Chat API and control plane
  |---------------- encrypted conversation objects ----> S3 + KMS
  |
  |---------------- TLS ----> allowlisted OpenRouter endpoint
  |
  +---------------- private VPC traffic ----> GPU EC2
                                               no public IP
                                               no public model port
```

The web interface does not connect directly to the GPU. Only the authenticated application entry point is exposed. The application can reach the model server over private VPC networking and remains available while the GPU is stopped.

The backend uses explicit dependency inversion:

```text
API and Pydantic schemas
          |
          v
Application use cases ----> Protocol ports
          |                       |
          v                       v
Domain rules              OpenRouter, Ollama/vLLM,
                          encryption, storage and AWS adapters
```

See [the architecture guide](docs/architecture.md) and [architecture decisions](docs/adr) for the reasoning behind these boundaries.

## Repository layout

```text
backend/        FastAPI service, domain logic, adapters and tests
frontend/       React/Vite interface and component tests
terraform/      AWS infrastructure with an optional private GPU host
docs/           Architecture, ADRs, design reference and threat model
ops/            Operational runbooks
.github/        Continuous-integration checks
```

## Local development

### Requirements

- Python 3.12
- Node.js 20 or later
- pnpm 11
- Terraform 1.8 or later for infrastructure validation

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Generate a local development key and place it in `.env` as described in [the backend guide](backend/README.md). Then start the API:

```powershell
uvicorn private_chat.main:app --reload
```

The development API listens on `http://127.0.0.1:8000`.

### Frontend

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

The interface starts with a local demonstration adapter. Configure the API base URL described in [the frontend guide](frontend/README.md) when connecting it to the backend.

### Terraform

Terraform defaults to no GPU instance. Read [the infrastructure guide](terraform/README.md), provide reviewed regional inputs, and inspect the complete plan before applying anything:

```powershell
cd terraform
Copy-Item terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out=tfplan
```

Do not apply this example to an AWS account until its IAM, state backend, authentication path and cost controls have been reviewed for that account.

Terraform requires `owner` and `cost_center` values and applies protected cost-allocation
tags to supported AWS resources automatically. After deployment, activate those tag keys
in AWS Billing and Cost Management before expecting them in Cost Explorer.

## Quality checks

```powershell
cd backend
ruff check .
mypy src
pytest

cd ../frontend
pnpm lint
pnpm test
pnpm build

cd ../terraform
terraform fmt -check -recursive .
terraform init -backend=false
terraform validate
```

Continuous integration runs the corresponding checks for pull requests and changes to the main branch.

## Security model

- The encrypted transcript is authoritative. Summaries and memories are derived, versioned data with provenance.
- Plaintext is present briefly in application RAM and model memory during inference; application-level encryption cannot protect active processing.
- Prompt and response bodies must never enter application, API Gateway, tracing or infrastructure logs.
- The browser must never receive OpenRouter or AWS credentials.
- OpenRouter policy is enforced inside its adapter so route handlers cannot accidentally omit it.
- The optional GPU is private compute. It receives no public IP, and its model port accepts traffic only from the application security group.
- Local encryption and repository adapters are development implementations. Production requires AWS KMS and durable encrypted storage adapters.

Read [SECURITY.md](SECURITY.md) and [the threat model](threat-model.md) before using real conversation data.

## Engineering principles

- Validate at boundaries with Pydantic and strict TypeScript.
- Encapsulate workflows in application services rather than routes or UI components.
- Depend on typed interfaces; select concrete infrastructure in a composition root.
- Keep security controls fail-closed and covered by regression tests.
- Prefer useful docstrings and decision comments over comments that repeat syntax.
- Keep changes small, typed, tested and reviewable.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the working agreement.

## Current limitations

- The included API has no production authentication or authorisation adapter.
- Durable S3/KMS repository adapters are still to be implemented and integration-tested.
- GPU AMIs, model licences, checksums, quotas and regional availability require a deployment-specific decision.
- The frontend uses demonstration data until connected to an authenticated API.
- This application is not a substitute for professional, medical, legal, financial or emergency support.
