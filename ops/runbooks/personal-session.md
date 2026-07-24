# Run a private personal chat session

This is the lowest-cost supported operating mode. React and FastAPI run on your
computer; the EC2 instance supplies GPU inference only. Systems Manager carries
an encrypted tunnel to Ollama without a public IP, inbound SSH, VPN, load
balancer, CloudFront distribution, ECS service, or Fargate task.

## One-time prerequisites

1. Install the AWS CLI and the AWS Session Manager plugin.
2. Authenticate the CLI with a short-lived identity in the deployment account.
3. Install Python 3.12, Node.js 20 or later, pnpm 11, and Terraform 1.9 or later.
4. Build and deploy the tested GPU AMI using the image-builder runbook.
5. Set `enable_gpu = true`, keep `enable_ssm_endpoints = false`, and set the
   approved AMI parameter in your Terraform variable file. For the initial reviewed plan,
   override only that safe default with `-var="enable_ssm_endpoints=true"` so the
   new instance can register with SSM. Record
   `terraform output -raw gpu_instance_id`.
6. Attach `application_data_policy_arn` to the local AWS identity only if the
   backend will use durable S3/KMS storage. The identity running the session also
   needs the dedicated `gpu_control_policy_arn` permissions.

The initial GPU creation starts chargeable compute. Stop it as soon as the first
readiness check is complete. A stopped instance retains its charged EBS volume;
terminate it when you no longer need fast session startup.

## Before each session

Create the hourly-billed private Systems Manager endpoints. The personal default
uses only the GPU's availability zone and the modern `ssm` and `ssmmessages`
services:

```powershell
cd terraform
$tfvars = "../.local/aws-build.tfvars" # Omit -var-file below if you use terraform.tfvars.
terraform plan -var-file $tfvars -var "enable_ssm_endpoints=true" -out ssm-on.tfplan
terraform apply ssm-on.tfplan
$instanceId = terraform output -raw gpu_instance_id
cd ..
```

If an older base image cannot register its SSM Agent, set
`ssm_endpoint_services = ["ssm", "ssmmessages", "ec2messages"]`, rebuild the
AMI with a current agent, then remove the compatibility endpoint.

## Open the Ollama tunnel

In the first PowerShell window:

```powershell
.\scripts\gpu-session.ps1 -InstanceId $instanceId
```

The script starts the GPU, waits for SSM readiness, and maps your local
`127.0.0.1:11434` to Ollama on the same port. Keep this window open. It stops the
GPU by default when the session ends. `-LeaveRunning` exists for controlled
maintenance but prints a cost warning.

For a command-line shell on the GPU instead of a tunnel:

```powershell
.\scripts\gpu-session.ps1 -InstanceId $instanceId -Mode Shell
```

This provides the same administrative outcome as an SSH terminal without
opening port 22 or managing an inbound SSH key. SSH-over-SSM is technically
possible, but is deliberately not configured because Session Manager already
provides the required shell and audit boundary.

## Start the local application

For disposable in-memory conversations, copy `backend/.env.example` to
`backend/.env` and generate the documented local master key. For durable
application-encrypted storage, use:

```dotenv
CHAT_STORAGE_BACKEND=s3
CHAT_CONVERSATION_BUCKET=<conversation_bucket_name>
CHAT_KMS_KEY_ID=<kms_key_arn>
CHAT_AWS_REGION=eu-west-2
CHAT_MODEL_BACKEND=self_hosted
CHAT_MODEL_NAME=private-chat
CHAT_SELF_HOSTED_BASE_URL=http://127.0.0.1:11434/v1
```

In a second PowerShell window:

```powershell
cd backend
uvicorn private_chat.main:app --host 127.0.0.1 --port 8000
```

In a third PowerShell window:

```powershell
cd frontend
pnpm dev
```

Open the local Vite address. The browser calls `/v1`; Vite proxies that path to
FastAPI on `127.0.0.1:8000`, and FastAPI calls Ollama through the SSM tunnel.
`CHAT_MODEL_NAME` must match `image_builder_model_name`, the Ollama name assigned
when the verified GGUF is imported into the AMI.

The GPU also has an independent systemd timer controlled by
`gpu_max_runtime_minutes` (two hours by default). It initiates an EC2 stop even
if this computer crashes and the script's normal cleanup cannot run.

## OpenRouter-only session (no GPU cost)

This is the alternative personal mode when inference may leave AWS through
OpenRouter. Do **not** start the GPU, create SSM endpoints, or open an Ollama
tunnel. The React frontend and encrypted conversation storage remain the same;
only the backend's inference adapter changes.

Before starting, set a key and a reviewed provider allowlist in the current
PowerShell session. The adapter still sends `data_collection: "deny"`, `zdr:
true`, disables provider fallbacks, and uses only these provider slugs.

```powershell
$env:CHAT_OPENROUTER_API_KEY = '<your key>'
$env:CHAT_OPENROUTER_ALLOWED_PROVIDERS = '<reviewed provider slug>'
.\scripts\start-openrouter-backend.ps1
```

In another terminal, start the unchanged frontend with `cd frontend; pnpm dev`.
Settings then provides five configured open-weight model choices. Pass
`-AllowCustomModel` only when you intentionally want to enter an arbitrary
OpenRouter model ID; otherwise the backend rejects IDs outside the five-model
catalogue. OpenRouter privacy controls reduce external retention and data
collection, but this is not equivalent to private GPU inference.

## End the session and stop charges

1. Close the frontend and backend processes.
2. Press Ctrl+C in the tunnel window. The session script requests an EC2 stop.
3. If the terminal was lost, run
   `.\scripts\stop-gpu.ps1 -InstanceId <instance-id>` immediately.
4. Confirm EC2 reports `stopped`.
5. Remove the hourly-billed endpoints:

```powershell
cd terraform
$tfvars = "../.local/aws-build.tfvars" # Omit -var-file below if you use terraform.tfvars.
terraform plan -var-file $tfvars -var "enable_ssm_endpoints=false" -out ssm-off.tfplan
terraform show -no-color ssm-off.tfplan
terraform apply ssm-off.tfplan
```

Do not delete the whole Terraform stack merely to end a session. Conversation
objects, KMS keys, AMIs and model artefacts have intentional retention controls.
See the [Terraform lifecycle guide](../../terraform/README.md#cost-and-lifecycle-choices)
before permanently retiring the project.
