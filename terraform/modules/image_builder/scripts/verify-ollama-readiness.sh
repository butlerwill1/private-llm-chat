#!/usr/bin/env bash
#
# Prove that the private vision model is genuinely ready for GPU inference.
#
# A successful /api/tags response only proves that Ollama's HTTP server and
# model manifest are available. It does not prove that the model runner has
# loaded its tensors, registered with Ollama's scheduler, or used the GPU.

set -Eeuo pipefail

readonly base_url="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
readonly model_name="${1:-private-vision}"
readonly warm_runs="${2:-3}"
readonly request_timeout_seconds="${OLLAMA_READINESS_TIMEOUT_SECONDS:-900}"
readonly image_base64='iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAXUlEQVR4nO3PAQ3AMAzAsPInvYOYrqySgyCes7w5ywOoA6gDqAOoA6gDqANYB5ifAwAAAAAAAAAAAAAAAAAAAAAAAAAAAAB4D/BaAHUAdQB1AHUAdQB1AHVTD9z2AWPS3g797R4gAAAAAElFTkSuQmCC'

if ! [[ "$warm_runs" =~ ^[1-9][0-9]*$ ]]; then
  echo "Warm run count must be a positive integer, received: $warm_runs" >&2
  exit 2
fi

readonly work_dir="$(mktemp --directory)"
readonly diagnostics_dir=/var/log/private-llm-chat
readonly run_timestamp="$(date --utc +%Y%m%dT%H%M%SZ)"
readonly log_file="$diagnostics_dir/ollama-readiness-$run_timestamp.log"
sampler_pid=''
diagnostics_printed=false

install --directory --owner root --group root --mode 0750 "$diagnostics_dir"
# Retain the complete probe output on the instance while also showing it in the
# Image Builder or SSM command output.
exec > >(tee --append "$log_file") 2>&1

stop_gpu_sampler() {
  if [ -n "$sampler_pid" ] && kill -0 "$sampler_pid" 2>/dev/null; then
    kill "$sampler_pid" 2>/dev/null || true
    wait "$sampler_pid" 2>/dev/null || true
  fi
  sampler_pid=''
}

print_diagnostics() {
  if [ "$diagnostics_printed" = true ]; then
    return
  fi
  diagnostics_printed=true
  stop_gpu_sampler

  echo '=== READINESS FAILURE DIAGNOSTICS ==='
  echo '--- UTC time ---'
  date --iso-8601=seconds || true
  echo '--- Ollama service status ---'
  systemctl status ollama.service --no-pager || true
  echo '--- Ollama service properties ---'
  systemctl show ollama.service \
    --property ActiveState \
    --property SubState \
    --property MainPID \
    --property NRestarts \
    --property ExecMainCode \
    --property ExecMainStatus || true
  echo '--- Recent Ollama journal ---'
  journalctl --unit ollama.service --no-pager --lines 400 || true
  echo '--- NVIDIA state ---'
  nvidia-smi || true
  echo '--- Ollama API process report ---'
  curl --silent --show-error --max-time 10 "$base_url/api/ps" || true
  echo
  echo '--- Process state ---'
  ps -eo pid,ppid,etimes,%cpu,%mem,rss,vsz,state,wchan:32,cmd --sort=-rss \
    | head --lines 80 || true
  echo '--- System memory and storage ---'
  free --human || true
  df --human / /var/lib/ollama || true
  echo '--- Kernel OOM events ---'
  journalctl --dmesg --no-pager \
    | grep --extended-regexp --ignore-case \
      'out of memory|oom-kill|killed process' \
    | tail --lines 100 || true
  echo "Diagnostics retained at $log_file"
}

cleanup() {
  local exit_code=$?
  stop_gpu_sampler
  if [ "$exit_code" -ne 0 ]; then
    print_diagnostics
  fi
  rm --force --recursive "$work_dir"
  exit "$exit_code"
}
trap cleanup EXIT

assert_completed_response() {
  local label=$1
  local response_file=$2

  if ! grep --extended-regexp --quiet \
    '"done"[[:space:]]*:[[:space:]]*true' "$response_file"; then
    echo "$label did not return Ollama's completed-response marker." >&2
    cat "$response_file" >&2 || true
    return 1
  fi
}

post_json() {
  local label=$1
  local endpoint=$2
  local payload=$3
  local response_file=$4
  local started_at
  local finished_at
  local curl_exit
  local http_code

  started_at=$(date +%s%3N)
  set +e
  http_code=$(curl --silent --show-error \
    --max-time "$request_timeout_seconds" \
    --output "$response_file" \
    --write-out '%{http_code}' \
    "$base_url$endpoint" \
    --header 'Content-Type: application/json' \
    --data-binary "$payload")
  curl_exit=$?
  set -e
  finished_at=$(date +%s%3N)

  echo "$label completed in $((finished_at - started_at)) ms (curl=$curl_exit HTTP=$http_code)."
  if [ "$curl_exit" -ne 0 ] || [ "$http_code" != 200 ]; then
    echo "$label failed." >&2
    cat "$response_file" >&2 || true
    return 1
  fi
}

echo "Testing Ollama readiness for model '$model_name' at $base_url."

tags_file="$work_dir/tags.json"
curl --fail --silent --show-error \
  --max-time 30 \
  --output "$tags_file" \
  "$base_url/api/tags"
if ! grep --fixed-strings --quiet "\"name\":\"$model_name" "$tags_file"; then
  echo "The required model '$model_name' is absent from /api/tags." >&2
  cat "$tags_file" >&2
  exit 1
fi
echo 'Model manifest is present in /api/tags.'

# Sample frequently enough to observe short warm requests. The first sample is
# often zero while curl is starting; the assertion below uses the maximum.
gpu_samples="$work_dir/gpu-utilisation.txt"
nvidia-smi \
  --query-gpu=utilization.gpu \
  --format=csv,noheader,nounits \
  --loop-ms=100 >"$gpu_samples" 2>&1 &
sampler_pid=$!

text_response="$work_dir/text-response.json"
text_payload=$(printf \
  '{"model":"%s","messages":[{"role":"user","content":"Reply with only the word ready."}],"stream":false,"think":false,"keep_alive":"30m","options":{"num_ctx":8192,"num_predict":8,"temperature":0}}' \
  "$model_name")
post_json 'Small text generation' '/api/chat' "$text_payload" "$text_response"
assert_completed_response 'Small text generation' "$text_response"

vision_payload=$(printf \
  '{"model":"%s","messages":[{"role":"user","content":"Return JSON with one key named shape describing the dark shape in this image.","images":["%s"]}],"stream":false,"think":false,"format":"json","keep_alive":"30m","options":{"num_ctx":8192,"num_predict":32,"temperature":0}}' \
  "$model_name" "$image_base64")

vision_response="$work_dir/vision-response.json"
post_json 'Cold-or-first vision generation' '/api/chat' "$vision_payload" "$vision_response"
assert_completed_response 'Cold-or-first vision generation' "$vision_response"

for run_number in $(seq 1 "$warm_runs"); do
  warm_response="$work_dir/warm-vision-$run_number.json"
  post_json "Warm vision generation $run_number/$warm_runs" \
    '/api/chat' "$vision_payload" "$warm_response"
  assert_completed_response "Warm vision generation $run_number/$warm_runs" "$warm_response"
done

process_file="$work_dir/processes.json"
curl --fail --silent --show-error \
  --max-time 30 \
  --output "$process_file" \
  "$base_url/api/ps"
if ! grep --fixed-strings --quiet "\"name\":\"$model_name" "$process_file"; then
  echo "The runner completed requests but '$model_name' is absent from /api/ps." >&2
  cat "$process_file" >&2
  exit 1
fi
echo 'The private model is registered as loaded in /api/ps.'

stop_gpu_sampler
max_gpu_utilisation=$(grep --extended-regexp '^[[:space:]]*[0-9]+' "$gpu_samples" \
  | awk 'BEGIN { max = 0 } { value = $1 + 0; if (value > max) max = value } END { print max }')
if [ -z "$max_gpu_utilisation" ] || [ "$max_gpu_utilisation" -le 0 ]; then
  echo 'No non-zero GPU utilisation was observed during generation.' >&2
  cat "$gpu_samples" >&2
  exit 1
fi

echo "Maximum observed GPU utilisation: $max_gpu_utilisation%."
echo "Ollama readiness passed; detailed output retained at $log_file."
