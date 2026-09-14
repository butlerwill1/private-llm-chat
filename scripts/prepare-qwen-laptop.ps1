$ErrorActionPreference = 'Stop'
$ollamaUrl = 'http://127.0.0.1:11434'

function Invoke-OllamaJson {
    param([string]$Endpoint, [hashtable]$Payload, [int]$TimeoutSeconds = 3600)
    Invoke-RestMethod -Uri "$ollamaUrl/api/$Endpoint" -Method Post `
        -ContentType 'application/json' -Body ($Payload | ConvertTo-Json -Depth 10) `
        -TimeoutSec $TimeoutSeconds
}

Write-Output 'Downloading Qwen 3.5 9B Q4 (joins an existing download if one is running)...'
Invoke-OllamaJson 'pull' @{ model = 'qwen3.5:9b'; stream = $false }

Write-Output 'Creating a 4K-context laptop preset (automatic GPU placement)...'
Invoke-OllamaJson 'create' @{
    model = 'qwen3.5:9b-laptop'
    from = 'qwen3.5:9b'
    parameters = @{ num_ctx = 4096 }
    stream = $false
}

# A short synthetic prompt verifies execution without using any private chat data.
Write-Output 'Testing the 9B model with a short response and thinking disabled...'
try {
    $reply = Invoke-OllamaJson 'generate' @{
        model = 'qwen3.5:9b-laptop'
        prompt = 'Reply with exactly: local model ready'
        think = $false
        stream = $false
        keep_alive = '5m'
        options = @{ num_ctx = 4096; num_predict = 32 }
    } 300
    Write-Output $reply.response
    $loaded = (Invoke-RestMethod "$ollamaUrl/api/ps").models |
        Where-Object { $_.name -eq 'qwen3.5:9b-laptop' } | Select-Object -First 1
    if ($loaded) {
        [pscustomobject]@{
            Model = $loaded.name
            AllocatedGiB = [math]::Round($loaded.size / 1GB, 2)
            VramGiB = [math]::Round($loaded.size_vram / 1GB, 2)
            Context = $loaded.context_length
            FullyOnGpu = ($loaded.size_vram -gt 0 -and $loaded.size_vram -eq $loaded.size)
        } | Format-List | Out-String | Write-Output
    }
} catch {
    Write-Warning "The 9B test failed: $($_.Exception.Message)"
} finally {
    # Release the test's memory; the next normal request will load it again.
    Invoke-OllamaJson 'generate' @{ model = 'qwen3.5:9b-laptop'; keep_alive = 0 } 60
}

Write-Output 'Downloading the larger Qwen 3.6 27B Q4 model...'
Invoke-OllamaJson 'pull' @{ model = 'qwen3.6:27b-q4_K_M'; stream = $false }
Write-Output 'Creating the CPU-only, 4K-context preset...'
Invoke-OllamaJson 'create' @{
    model = 'qwen3.6:27b-cpu'
    from = 'qwen3.6:27b-q4_K_M'
    parameters = @{ num_ctx = 4096; num_gpu = 0 }
    stream = $false
}

$freeGiB = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
Write-Output ('Available system RAM: {0:N1} GiB. The CPU model has been downloaded but not loaded.' -f $freeGiB)
Write-Output 'Close other applications before loading the CPU model; aim for at least 22 GiB available RAM.'
Write-Output 'Ready: ollama run qwen3.5:9b-laptop'
Write-Output 'CPU:   ollama run qwen3.6:27b-cpu'
