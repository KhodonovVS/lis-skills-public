# LLM Container Management in Proxmox LXC

## CT 127 — llm-hermes (Gemma 4 31B)

| Property | Value |
|----------|-------|
| CT ID | 127 |
| Hostname | llm-hermes |
| IP | <адрес из окружения> |
| Docker container | `hermes-llm` |
| Image | `ghcr.io/ggml-org/llama.cpp:server-cuda` |
| Port | 8000 |
| API | `http://<адрес из окружения>/v1` |
| Model | Gemma 4 31B Q4_K_M (~18 GB) |
| GPUs | 3× RTX 3060 (12 GB each, 36 GB total VRAM) |
| Auth | None (local network only) |

## Common Failure Modes

### Exit code 139 (segfault / OOM)

The container crashed with exit code 139 — typically an out-of-memory condition or GPU driver issue.

**Restart:**
```bash
# From Proxmox host:
lxc-attach 127 -- docker restart hermes-llm

# Wait ~40-60 seconds for model to load (check via API)
HTTP-запрос к http://<адрес из окружения>/v1/models
# Returns {"error":{"message":"Loading model","type":"unavailable_error","code":503}}
# → Then later returns model list (200 OK) when ready
```

The model takes ~30-60 seconds to load into GPU memory. During loading, the API returns HTTP 503 with "Loading model".

### Docker daemon not running

```bash
lxc-attach 127 -- systemctl restart docker
lxc-attach 127 -- docker start hermes-llm
```

### CUDA/GPU issues

```bash
# Check GPU visibility inside container
lxc-attach 127 -- docker exec hermes-llm nvidia-smi

# Check available VRAM
lxc-attach 127 -- nvidia-smi
```

## Monitoring

```bash
# Check if server is alive
HTTP-запрос к http://<адрес из окружения>/v1/models

# Check model metadata
HTTP-запрос к http://<адрес из окружения>/v1/models (разбор ответа) -m json.tool

# Quick chat completion test
HTTP-запрос к http://<адрес из окружения>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma-4-31b","messages":[{"role":"user","content":"say OK"}],"max_tokens":10}' (разбор ответа) -m json.tool
```

## Hermes Profile for Operator

The `operator` Hermes profile connects to this server:

```yaml
model:
  default: gemma-4-31b
  provider: custom
  base_url: http://<адрес из окружения>/v1
  context_length: 131072  # llama.cpp default; model training ctx is 262144
  max_tokens: 4096
agent:
  max_turns: 60
  reasoning_effort: high
display:
  show_reasoning: true
```

Note: The `context_length` must be ≥ 64K (Hermes minimum), otherwise the agent refuses to start. Gemma 4 31B trains at 262K context, and llama.cpp serves it at 131K by default (with flash-attn), so 131072 is the correct value.

## Performance Metrics

From real benchmarks on 3× RTX 3060, Gemma 4 31B Q4_0:

| Metric | Value |
|--------|-------|
| Prompt prefill speed | ~150-160 t/s |
| Generation (decoding) speed | **~17.3 t/s** |
| Time per token | ~57.6 ms |
| Time for 100 tokens | ~6 s |
| Time for 1000 tokens | ~58 s |

All measurements from llama.cpp's `timings` field in API responses.

## Model Behavior: Thinking Mode

Gemma 4 31B (via llama.cpp) has a notable behavioral quirk:

- **All responses go to `reasoning_content`**, not `content` — the model defaults to thinking/reasoning mode
- Setting `chat_template_kwargs: {"thinking": false}` in the request does NOT reliably disable it — the model still fills `reasoning_content` with its chain of thought
- The `content` field is often empty or null even when `finish_reason: "stop"` or `"length"`
- This means the model's actual answer may be embedded inside `reasoning_content`, not in `content`
- Hermes subagents may receive empty `content` and show no visible output — this is the model's behavior, not a bug

**Workaround:** If you need to extract the final answer:
1. Parse `reasoning_content` as the primary field
2. The model may need a very explicit prompt to output final text to `content` (e.g., "Output your final answer after ---FINAL---")
3. For most Hermes agent use (operator role), the model works fine — it just "thinks aloud" in reasoning_content

## When the Operator Task Fails Mid-way

If the operator (Gemma 4 31B) crashes mid-task (e.g., server goes down):
1. Restart the container (see above)
2. Re-run the operator task — the subagent will continue where it left off
3. Use `NOT EXISTS` checks in SQL to avoid duplicate inserts
