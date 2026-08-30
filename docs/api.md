# API Reference

Base URL: `http://<host>:8080/api/v1`

All endpoints require authentication (session cookie) except `/health*`.

## Authentication

```bash
# Login
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}' \
  -c cookies.txt

# Use cookie for subsequent requests
curl -b cookies.txt http://localhost:8080/api/v1/...

# Logout
curl -X POST http://localhost:8080/api/v1/auth/logout -b cookies.txt
```

## Health & Readiness

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /health` | No | Liveness probe (always 200 if process alive) |
| `GET /health/ready` | No | Deep readiness (DB + modules + config) |

```bash
curl http://localhost:8080/health/ready
# {"status":"ready","checks":{"db":true,"config":true,"modules":true}}
```

## Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/config` | GET | Get current config (secrets redacted) |
| `/config` | PATCH | Update config (merge) |

```bash
# Get config
curl -b cookies.txt http://localhost:8080/api/v1/config

# Enable offline mode
curl -X PATCH -b cookies.txt http://localhost:8080/api/v1/config \
  -H "Content-Type: application/json" \
  -d '{"offline_mode": true}'
```

## Providers

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/providers` | GET | List all providers with status |
| `/providers/{name}` | GET | Get provider config |
| `/providers/{name}` | PATCH | Update provider (enable/disable, model) |

```bash
# List providers
curl -b cookies.txt http://localhost:8080/api/v1/providers

# Enable OpenAI
curl -X PATCH -b cookies.txt http://localhost:8080/api/v1/providers/openai \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "model": "gpt-4o"}'
```

## Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat/sessions` | GET | List chat sessions |
| `/chat/sessions` | POST | Create new session |
| `/chat/sessions/{id}` | GET | Get session with messages |
| `/chat/sessions/{id}` | DELETE | Delete session |
| `/chat/sessions/{id}/messages` | POST | Send message (streaming) |

```bash
# Create session
curl -X POST -b cookies.txt http://localhost:8080/api/v1/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"title": "New chat"}'

# Send message (SSE stream)
curl -X POST -b cookies.txt http://localhost:8080/api/v1/chat/sessions/{id}/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"content": "Hello, world!", "provider": "auto"}'
```

## Agents

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agents` | GET | List agents |
| `/agents` | POST | Create agent |
| `/agents/{id}` | GET | Get agent |
| `/agents/{id}` | PATCH | Update agent |
| `/agents/{id}` | DELETE | Delete agent |
| `/agents/{id}/run` | POST | Run agent task |

```bash
# Create agent
curl -X POST -b cookies.txt http://localhost:8080/api/v1/agents \
  -H "Content-Type: application/json" \
  -d '{"name": "Researcher", "model": "gpt-4o", "tools": ["web_search"]}'

# Run task
curl -X POST -b cookies.txt http://localhost:8080/api/v1/agents/{id}/run \
  -H "Content-Type: application/json" \
  -d '{"task": "Summarize latest AI news"}'
```

## Workflows

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/workflows` | GET | List workflows |
| `/workflows` | POST | Create workflow |
| `/workflows/{id}` | GET | Get workflow |
| `/workflows/{id}/run` | POST | Execute workflow |

## Memory

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/memory` | GET | List memories |
| `/memory` | POST | Create memory |
| `/memory/search` | POST | Semantic search |
| `/memory/{id}` | DELETE | Delete memory |

## Boards (Kanban)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/boards` | GET | List boards |
| `/boards` | POST | Create board |
| `/boards/{id}` | GET | Get board with columns/cards |
| `/boards/{id}/columns` | POST | Add column |
| `/boards/{id}/cards` | POST | Add card |

## Skills

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/skills` | GET | List installed skills |
| `/skills` | POST | Install skill (from URL/registry) |
| `/skills/{name}` | DELETE | Uninstall skill |

## AIOps

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/aiops/runs` | GET | List AIOps runs |
| `/aiops/runs` | POST | Trigger AIOps run |
| `/aiops/runs/{id}` | GET | Get run details |

## Settings

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/settings` | GET | Get all settings |
| `/settings` | PATCH | Update settings |

## Error Responses

All errors follow RFC 7807 (Problem Details):

```json
{
  "type": "https://hivestack.dev/errors/provider-disabled",
  "title": "Provider Disabled",
  "status": 403,
  "detail": "Provider 'openai' is disabled. Enable in Settings or set offline_mode=false.",
  "instance": "/api/v1/chat/sessions/123/messages",
  "code": "PROVIDER_DISABLED"
}
```

### Common Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `PROVIDER_DISABLED` | 403 | offline_mode=true or provider not enabled |
| `INVALID_CREDENTIALS` | 401 | Wrong username/password |
| `SESSION_EXPIRED` | 401 | Cookie expired, re-login |
| `VALIDATION_ERROR` | 422 | Request body validation failed |
| `NOT_FOUND` | 404 | Resource doesn't exist |
| `RATE_LIMITED` | 429 | Too many requests |

## Rate Limits

- Auth endpoints: 10 req/min per IP
- Chat/Agents: 60 req/min per session
- Provider calls: provider-specific (passed through)

## WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `WS /ws/chat/{session_id}` | Real-time chat messages |
| `WS /ws/agents/{agent_id}` | Agent execution updates |
| `WS /ws/workflows/{workflow_id}` | Workflow progress |

```javascript
const ws = new WebSocket("ws://localhost:8080/ws/chat/123", ["session-cookie"]);
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

## OpenAPI Spec

```bash
# Download OpenAPI JSON
curl http://localhost:8080/openapi.json > openapi.json

# Or visit Swagger UI
open http://localhost:8080/docs
```