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
