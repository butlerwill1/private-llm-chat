# Helper scripts

The PowerShell scripts in this directory support the documented personal
workflows. Read the linked runbook before using a script that changes AWS state.

| Script | Purpose | AWS effect |
|---|---|---|
| `gpu-session.ps1` | Starts a private GPU session and opens an Ollama tunnel or Session Manager shell. | Starts the selected EC2 instance; normally stops it when the session closes. |
| `stop-gpu.ps1` | Emergency cost-control helper after a lost session. | Stops one explicitly supplied EC2 instance. |
| `stage-model.ps1` | Downloads a pinned GGUF, verifies it and uploads it to the approved model bucket. | Creates a model object in S3; does not start a GPU. |
| `start-openrouter-backend.ps1` | Starts FastAPI in OpenRouter-only mode. | Does not call AWS, start a GPU or create endpoints. |
| `test-gpu-readiness.ps1` | Runs bounded text, vision, scheduler and GPU-utilisation checks, with automatic failure diagnostics. | Executes a read-only inference test on one already-running GPU through SSM; it does not pull models or expose a port. |

Scripts do not replace Terraform. Terraform owns the long-lived infrastructure;
the session helpers perform short-lived operational actions such as starting an
already-created EC2 instance or opening a local tunnel.
# Local default launcher

`start-local-chat.ps1` starts the normal loopback-only application: encrypted
local SQLite storage plus privacy-restricted OpenRouter inference. It does not
create, start or contact AWS resources. Copy `backend/.env.example` to
`backend/.env`, set the OpenRouter API key, then run it from the repository root.

The key in `.env` is plaintext but ignored by Git; treat it as a spend-capable
credential. The conversation-encryption key is stored separately using Windows
DPAPI and has no recovery export.
