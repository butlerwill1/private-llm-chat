# Ollama: a practical local-model guide

Ollama runs downloaded language models on this computer. In this project it is
the local inference engine: Private Chat sends it requests over the loopback-only
address `http://127.0.0.1:11434`.

This guide is for experimenting directly in PowerShell. It does not contact AWS.

## See what is installed

```powershell
ollama list
```

This lists downloaded models, their ID, disk size and modification time. A
model can be downloaded without currently using GPU memory.

Show the technical metadata for one model:

```powershell
ollama show gemma3:4b
```

Useful fields include parameter count, quantization, maximum context length,
and supported capabilities such as text completion or vision.

## Run a one-off prompt

```powershell
ollama run gemma3:4b "Explain what a KV cache is in two short paragraphs."
```

The first prompt after a model is unloaded is a **cold start**: Ollama loads
its weights and working memory into GPU VRAM. A follow-up prompt is normally
faster while the model remains warm.

For an interactive session, omit the prompt:

```powershell
ollama run gemma3:4b
```

Type a question, press Enter, then use `/bye` to leave the session.

## Download another model

```powershell
ollama pull llama3.2:3b
```

`pull` first retrieves a small **manifest** (the model's index), then downloads
the referenced data blobs and verifies their SHA-256 digests. It is safe to run
again: Ollama reuses verified data already on disk.

Check that it completed:

```powershell
ollama list
ollama show llama3.2:3b
```

On this laptop, favor small quantized models around 3B–4B parameters. They leave
more of the 8 GB VRAM available for Windows, runtime buffers and the KV cache.

## See what is currently using memory

```powershell
ollama ps
nvidia-smi
```

`ollama ps` shows models currently loaded by Ollama, including their context
length and Ollama-reported VRAM allocation. `nvidia-smi` shows GPU-wide VRAM
use, temperature, power and utilization. The two values can differ because
Windows and other GPU processes also consume VRAM.

For GPU inference, `ollama ps` must identify a GPU processor and show non-zero
VRAM use. If it says `100% CPU`, the model is running successfully but is not
using the GPU; inspect `%LOCALAPPDATA%\Ollama\server.log` before treating it
as a GPU-ready setup.

Unload a warm model when you want to release its VRAM:

```powershell
ollama stop gemma3:4b
```

This does **not** delete the downloaded model; it only stops the currently
loaded runner. The next prompt will cold-start it again.

## Remove a downloaded model

First confirm the exact name with `list`, then remove it:

```powershell
ollama rm llama3.2:3b
```

This frees its model data from disk. Do not delete individual files under
`.ollama\models\blobs` by hand: blobs can be shared by multiple models.

## Local HTTP API

Ollama also exposes a local API. This is what the Private Chat backend uses.

```powershell
$body = @{
  model = 'gemma3:4b'
  prompt = 'Give three ideas for a short walk after work.'
  stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:11434/api/generate' `
  -ContentType 'application/json' `
  -Body $body
```

List loaded models through the API:

```powershell
Invoke-RestMethod 'http://127.0.0.1:11434/api/ps'
```

The API is local to this machine. Do not expose port `11434` to a network.

## Storage layout

By default, downloaded model data is stored under:

```text
C:\Users\<your-Windows-user>\.ollama\models
```

`manifests` contains one small index per model tag. `blobs` is a shared pool of
the actual weight and support files, named by SHA-256 content digest. This is
why there is not a separate folder of blobs per model.

## Useful learning sequence

```powershell
# 1. Inspect the installed model.
ollama list
ollama show gemma3:4b

# 2. Run a prompt, then see its loaded state and GPU usage.
ollama run gemma3:4b "What is the difference between RAM and VRAM?"
ollama ps
nvidia-smi

# 3. Release GPU memory without deleting the model.
ollama stop gemma3:4b
```

The Private Chat **System Monitor** is intended to make the same operational
information visible from the app while retaining only privacy-safe performance
telemetry.

## Qwen laptop and CPU presets

Run the preparation script to download both models, create the presets and
test the smaller model using a short synthetic prompt:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare-qwen-laptop.ps1
```

The presets reuse the original model blobs; they do not duplicate the weights.

| Preset | Base model | Execution | Configured context |
| --- | --- | --- | --- |
| `qwen3.5:9b-laptop` | `qwen3.5:9b` (Q4_K_M, about 6.6 GB) | Ollama automatically chooses GPU or mixed placement | 4,096 tokens |
| `qwen3.6:27b-cpu` | `qwen3.6:27b-q4_K_M` (about 17 GB) | CPU only (`num_gpu=0`) | 4,096 tokens |

```powershell
ollama run qwen3.5:9b-laptop
ollama ps
nvidia-smi
```

`100% GPU` in `ollama ps` confirms full GPU placement. Other GPU applications
or a larger context allocation can change whether the smaller model fits.
On this RTX 5050 laptop, the preparation test on 13 September 2026 completed
fully on GPU: Ollama reported 5.11 GiB allocated in VRAM at 4,096 tokens for
a text-only prompt with thinking disabled. The larger CPU preset was downloaded
and its settings verified, but it was not loaded because free system RAM was
only about 4.8 GiB.
The standard `qwen3.6:27b-q4_K_M` tag retains automatic placement and can use
both CPU and GPU; the `27b-cpu` preset explicitly selects CPU execution.

Before experimenting with the larger model, release any loaded smaller model
and close memory-heavy applications. Aim for at least 22 GiB of available
system RAM as an initial allowance for its weights, working memory and context.
This is a practical starting point, not a guarantee; monitor memory while loading.
The preparation script downloads the larger model but deliberately does not
load it when existing applications already occupy most of the laptop's RAM.

```powershell
ollama stop qwen3.5:9b-laptop
ollama run qwen3.6:27b-cpu
ollama ps
```

The CPU preset should report `100% CPU`. Downloading a model alone consumes
disk space; running it consumes RAM/VRAM. CPU inference can be substantially
slower, particularly with thinking enabled.

With `CHAT_ENABLE_LOCAL_OLLAMA=true`, Private Chat's model dropdown exposes
Gemma 3 4B, Qwen 3.5 9B (local GPU, automatic placement), and Qwen 3.6 27B
(local CPU). The Qwen choices use the prepared preset tags above, including
their 4K context and the larger model's CPU-only setting. Changing the dropdown
updates the conversation's active model; the next message runs that model.
Selecting a model alone does not load its weights.

The approved local list can be changed with `CHAT_LOCAL_OLLAMA_ROUTES`, a JSON
array of objects with `model_id` and `label`. Restart the backend and refresh
the browser after changing the catalogue. `CHAT_LOCAL_OLLAMA_MODEL_NAME` remains
supported for an additional custom local tag. Downloading an arbitrary model
does not automatically add it to the approved dropdown list.
