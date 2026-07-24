# Helper scripts

The PowerShell scripts in this directory support the documented personal
workflows. Read the linked runbook before using a script that changes AWS state.

| Script | Purpose | AWS effect |
|---|---|---|
| `gpu-session.ps1` | Starts a private GPU session and opens an Ollama tunnel or Session Manager shell. | Starts the selected EC2 instance; normally stops it when the session closes. |
| `stop-gpu.ps1` | Emergency cost-control helper after a lost session. | Stops one explicitly supplied EC2 instance. |
| `stage-model.ps1` | Downloads a pinned GGUF, verifies it and uploads it to the approved model bucket. | Creates a model object in S3; does not start a GPU. |
| `start-openrouter-backend.ps1` | Starts FastAPI in OpenRouter-only mode. | Does not call AWS, start a GPU or create endpoints. |

Scripts do not replace Terraform. Terraform owns the long-lived infrastructure;
the session helpers perform short-lived operational actions such as starting an
already-created EC2 instance or opening a local tunnel.
