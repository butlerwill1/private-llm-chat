# Private GPU AMI factory

This module defines a manually triggered EC2 Image Builder pipeline for the
private Ollama runtime. Creating the pipeline does not build an image. A build
runs only when an operator starts the pipeline or explicitly sets
`build_image_now = true`, and it uses chargeable GPU build and test instances.

## Supply-chain controls

- The parent is an explicit AMI ID and must resolve to an AWS-owned image.
- Build validation fails unless the base image exposes a working NVIDIA GPU.
- The exact Ollama version is downloaded from its versioned GitHub release URL.
- The caller supplies the release SHA-256; extraction happens only after it
  matches. The component never executes the remote install script.
- An optional private GGUF model is read from one exact S3 object and imported
  only after its supplied SHA-256 matches.
- Build provenance is recorded in `/etc/private-llm-chat/image-build.json`.

## Network boundaries

Ephemeral build and test instances use a dedicated VPC and security group with
no ingress. HTTPS egress is necessary to retrieve the pinned Ollama release and
reach AWS APIs. This network is separate from the isolated runtime VPC. The AMI's
systemd service listens on the model port, but the runtime security group permits
that port only from application compute and assigns no public address.

## Approval flow

The test phase checks NVIDIA, systemd, the exact Ollama version, and its local
API. When a model is included, the shared readiness probe performs text
generation, vision generation, three consecutive warm vision requests, confirms
the model appears in `/api/ps`, and samples `nvidia-smi` to require non-zero GPU
utilisation. A timeout captures service status, the journal, GPU and process
state, memory, storage and kernel OOM events in
`/var/log/private-llm-chat/ollama-readiness-*.log`.

Successful distribution keeps the AMI private and publishes its ID to the
module's typed `aws:ec2:image` SSM parameter. A later Terraform run may set
`gpu_ami_ssm_parameter_name` to consume it. This two-step flow prevents a failed
or still-running build from becoming the runtime image.

The service pins `OLLAMA_LLM_LIBRARY=cuda_v12`. Ollama documents this override
as the fallback when automatic LLM-library detection is unreliable. The image
test still runs real inference and requires non-zero GPU allocation, so the
override cannot make a broken CUDA installation pass.

At boot, a bounded systemd pre-start probe runs Ollama's actual CUDA backend
until it enumerates a GPU. This prevents an early service start from permanently
falling back to CPU while the EC2 GPU driver is still initialising. Tests also
check CUDA selection before loading the model, avoiding a long CPU-only cold
load. Candidate AMIs are tagged `ImageStatus=candidate`; the typed SSM parameter
is the approval signal because Image Builder creates the AMI before testing it.

The single-model service explicitly uses one runner and one parallel request,
keeps the runner warm for 30 minutes, and uses an 8K context for vision-heavy
PDF prompts. `LLAMA_ARG_CACHE_RAM=512` bounds llama.cpp's otherwise 8 GiB
persistent prompt cache. This matters on `g6.xlarge`, which has 16 GiB host RAM;
mostly unique PDF pages obtain little benefit from retaining an 8 GiB prompt
cache.

AWS component and recipe semantic versions are immutable. Bump the component
version for template changes and the recipe version for recipe/input changes.
The deployment identity must be able to pass the two module-created Image Builder
roles. Model objects encrypted with a customer KMS key must use the configured
build key or grant the builder role equivalent decrypt access.
