# Running an LLM on a GPU: Ollama runner readiness postmortem

**Date:** 28 July 2026  
**Type:** Incident and learning note  
**Severity:** Major for the PDF benchmark  
**Model:** `private-vision:latest` — Qwen 3.5 9B, Q4_K_M, vision-capable  
**Hardware:** AWS `g6.xlarge`, with an NVIDIA L4 GPU (about 23 GB VRAM) and 16 GB system RAM

## Summary

The private Ollama service could answer `/api/tags`, and the installed vision model appeared in the model list, but `/api/chat` requests could hang for minutes. During a hang, the CUDA runner (`llama-server`) held about 5 GB of GPU VRAM while GPU utilisation was 0%. At the same time, `/api/ps` returned an empty list.

The important distinction is that copying model weights to GPU memory is only one stage of loading a model. The runner must also complete its startup checks and report healthy to Ollama’s scheduler. Until then, it is not listed in `/api/ps` and cannot serve inference reliably.

The fix was to bound the llama.cpp prompt cache, increase the vision context, keep the model warm for longer, and add an end-to-end readiness test. The corrected system passed two cold lifecycle tests and fifteen warm vision requests.

## What happened

The client sent one PDF-page image at a time:

```text
POST /api/chat
model: private-vision
stream: false
think: false
format: json
temperature: 0
timeout: 300 seconds
```

The failure sequence was:

1. `/api/tags` worked. This proved that Ollama’s HTTP service and model manifest were available, not that the model was ready to infer.
2. Ollama started a CUDA `llama-server` process.
3. Logs showed all 34 model layers offloaded to the GPU, using a 4,861 MiB CUDA model buffer and 546 MiB CPU model buffer.
4. The runner then stopped making readiness progress. It held VRAM but used 0% of the GPU.
5. Because the health handshake had not completed, Ollama’s scheduler did not add the model to `/api/ps`.
6. The waiting API request timed out or was cancelled. Ollama logged `Load failed ... context canceled`, discarded the runner, and retried with a new PID.
7. Repeated client retries could create a load/cancel/reload loop.

Restarting Ollama temporarily broke the cycle. A cold one-page vision request took about 40 seconds, including 37 seconds of loading; an immediate warm request took 2.87 seconds. The underlying configuration still needed fixing.

## Three different kinds of model memory

| Memory area | Where it lives | Purpose | What happened |
|---|---|---|---|
| Model weights | Mostly GPU VRAM | Learned parameters used for every prediction | About 4.86 GB loaded to the L4 GPU. This part worked. |
| KV cache / request context | Usually GPU VRAM | Attention keys and values for the current request or conversation | The prior 4,096-token limit was too small for some PDF image requests. One measured 4,639 tokens. |
| Prompt cache | System RAM in llama.cpp | Saves finished prompts so similar prompts can reuse work | Default capacity was 8,192 MiB, too large for a 16 GB host processing mostly unique PDF pages. |

### Was there automatic clearing?

Yes. The prompt cache was not unbounded. llama.cpp removed the oldest prompt after it reached its configured capacity:

```text
cache size limit reached, removing oldest entry
```

The problem was that the capacity was allowed to reach 8 GiB before eviction began. The host has about 15 GiB usable RAM and no swap. The runner reached roughly 10 GB resident memory, leaving limited headroom for Ollama, the operating system and model lifecycle work.

A large prompt cache is useful for repeated chat history. It gives little benefit when processing mostly unique PDF pages.

## Root causes

### Oversized host-RAM prompt cache

The runner defaulted to `--cache-ram 8192`. This was a poor fit for a `g6.xlarge`: the GPU had spare VRAM, but the host had only 16 GB RAM.

The prompt cache was not proven to be the sole source of every early stall; the earliest stalls occurred just after `load_tensors`. It did, however, create avoidable host-memory pressure and made runner lifecycle behaviour less robust.

### Client cancellation during readiness

The scheduler recorded:

```text
Load failed ... timed out waiting for llama-server to start: context canceled
```

The request that triggered the load was cancelled before the runner had completed its readiness handshake. This explains the confusing state where the runner had already allocated VRAM but was not in `/api/ps`.

### Context window too small for some vision requests

The old service used a 4,096-token context. Image tokenisation plus a PDF page and prompt can exceed that. The service logged:

```text
request (4639 tokens) exceeds the available context size (4096 tokens)
```

This is a separate explicit error, rather than the readiness hang, but it still made the PDF benchmark unreliable.

### Short default keep-alive

Ollama normally keeps a model loaded for five minutes after a request. This is sensible for general use, but a longer batch job with pauses can then trigger unnecessary cold loads.

## Fix applied

Only Ollama was restarted; the EC2 instance was not replaced and no other model was started.

```ini
[Service]
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_QUEUE=8
Environment=OLLAMA_CONTEXT_LENGTH=8192
Environment=OLLAMA_KEEP_ALIVE=30m
Environment=LLAMA_ARG_CACHE_RAM=512
```

- `OLLAMA_MAX_LOADED_MODELS=1`: serves exactly one model, preventing a second runner from consuming memory.
- `OLLAMA_NUM_PARALLEL=1`: serialises inference, appropriate for one user and one benchmark worker.
- `OLLAMA_MAX_QUEUE=8`: prevents a very large backlog concealing a stuck service.
- `OLLAMA_CONTEXT_LENGTH=8192`: allows image-plus-PDF prompts larger than the old 4K limit.
- `OLLAMA_KEEP_ALIVE=30m`: keeps the runner warm during a batch.
- `LLAMA_ARG_CACHE_RAM=512`: caps persistent prompt-cache RAM at 512 MiB instead of 8 GiB.

The source Image Builder templates were also updated, so a future AMI can include these settings rather than relying on a manual live fix.

## Readiness test added

Two reusable tests were added:

- `scripts/test-gpu-readiness.ps1` runs the probe through AWS Systems Manager Run Command against one named GPU instance.
- `terraform/modules/image_builder/scripts/verify-ollama-readiness.sh` is baked into future AMIs and is used in the Image Builder test stage.

The probe:

1. Calls `/api/tags` and confirms the required model exists.
2. Sends a small text generation request.
3. Sends a small vision request with a deterministic image.
4. Repeats the vision request while the model is warm.
5. Calls `/api/ps` and confirms that `private-vision` is registered as loaded.
6. Samples `nvidia-smi` every 100 ms and requires non-zero GPU utilisation.
7. On failure, captures systemd status, the Ollama journal, `nvidia-smi`, `/api/ps`, process state, memory, disk and kernel OOM events.

Failure output is retained on the GPU instance at:

```text
/var/log/private-llm-chat/ollama-readiness-<timestamp>.log
```

## Verification results

The existing SSM tunnel remained the only laptop-facing API route: `http://127.0.0.1:11434`. Ollama was not exposed directly to the internet.

| Test | Result |
|---|---|
| First corrected cold text request | About 26 seconds |
| First corrected vision request | 0.95 seconds |
| Five warm vision requests | About 0.53 seconds each |
| Second warm sequence | Ten requests at about 0.52–0.54 seconds each |
| Second cold lifecycle test | Passed after deliberately restarting Ollama |
| Maximum observed GPU utilisation | 96% |
| Scheduler state | `/api/ps` listed `private-vision` throughout |
| Runner resident memory | Fell from about 10 GB to about 1.48 GB |
| Available host RAM | Rose from about 4.2 GB to about 12 GB |

Fifteen consecutive warm vision requests passed. No subsequent Ollama self-restart or new runner-load failure was observed.

## What each diagnostic means

| Check | What it proves | What it does not prove |
|---|---|---|
| `/api/tags` | Ollama is reachable and knows the model manifest | The model runner is loaded or can generate |
| `/api/ps` | Ollama’s scheduler considers a runner loaded and ready | The next complex prompt will fit in context |
| `nvidia-smi` VRAM use | A process allocated GPU memory | The GPU is actively calculating or the runner is healthy |
| `nvidia-smi` GPU utilisation | The GPU was working at the sampling moment | Requests were correctly routed and completed |

The original state—VRAM allocated, 0% GPU use and an empty `/api/ps`—therefore meant: a lower-level runner existed, but had not become a ready Ollama model.

## Pinned Ollama version

The live instance remained on Ollama `0.32.1`. The unchanged version became reliable after the configuration fix, so the pinned version was not demonstrated to be the primary cause.

A future AMI can use Ollama `0.32.3`, which includes an updated llama.cpp engine. That should still be validated by the same readiness test rather than assumed to fix an issue by itself.

## Useful commands

Run the full remote readiness test from this repository:

```powershell
.\scripts\test-gpu-readiness.ps1 `
  -InstanceId i-0e1a8d8a6e6cbeebe `
  -Model private-vision `
  -WarmRuns 5
```

Useful read-only checks in an SSM shell:

```bash
curl -s http://127.0.0.1:11434/api/tags
curl -s http://127.0.0.1:11434/api/ps
nvidia-smi
nvidia-smi dmon -s pucm
systemctl status ollama
journalctl -u ollama -n 200 --no-pager
free -h
```

## Key learnings

1. A model appearing in `/api/tags` is not the same as a model being ready for inference.
2. GPU VRAM allocation is not proof of healthy GPU inference. Check a real completion, `/api/ps` and GPU utilisation.
3. System RAM matters even when most model weights run on a GPU.
4. Cache defaults must suit the workload. Large prompt caches are poor value for unique PDF pages.
5. Cold and warm tests answer different questions: cold tests validate lifecycle; warm tests validate repeated inference.
6. A deliberately constrained personal deployment is easier to operate: one model, one worker and a bounded queue.
7. Run readiness checks before an expensive batch benchmark.

## Follow-up actions

- [x] Apply lifecycle settings to the live Ollama service.
- [x] Add the readiness probe to the repository and Image Builder test stage.
- [x] Verify two cold starts and fifteen warm vision requests.
- [x] Keep Ollama private behind the localhost SSM tunnel.
- [ ] Build and validate the next AMI revision with the corrected settings and Ollama 0.32.3.
- [ ] Restart the full 50-PDF benchmark from a clean run.

## Related repository files

- `scripts/test-gpu-readiness.ps1`
- `terraform/modules/image_builder/scripts/verify-ollama-readiness.sh`
- `terraform/modules/image_builder/components/install-ollama.yaml.tftpl`
- `terraform/modules/image_builder/components/test-ollama.yaml.tftpl`

