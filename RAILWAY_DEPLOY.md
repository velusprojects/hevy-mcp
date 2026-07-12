# Railway Deployment Playbook

Step-by-step guide for deploying this MCP server to Railway, designed to be followed by a human or automated by an agent with the Railway MCP tools.

## Prerequisites

- Railway CLI installed and authenticated (`railway login`)
- Railway MCP server connected (for agent-driven deploys)
- `.env` file with `HEVY_API_KEY` set
- Dockerfile in project root

## Steps

### 1. Check Railway CLI status

```
Tool: check-railway-status
```

Verify the CLI is installed and the user is logged in before proceeding.

### 2. Create project and link

```
Tool: create-project-and-link
Params:
  projectName: "hevy-mcp"
  workspacePath: <repo root>
```

Creates the Railway project and links the local directory. This auto-links to the `production` environment.

### 3. Deploy (creates the service)

```
Tool: deploy
Params:
  workspacePath: <repo root>
```

First deploy uploads the Dockerfile and creates a service named after the project. The service must exist before you can set variables or generate a domain.

### 4. Link the service

```
Tool: link-service
Params:
  workspacePath: <repo root>
  serviceName: "hevy-mcp"
```

Explicitly link the service so subsequent commands target it.

### 5. Set environment variables

```
Tool: set-variables
Params:
  workspacePath: <repo root>
  variables: ["HEVY_API_KEY=<key>", "ENVIRONMENT=production"]
```

Setting variables triggers a redeploy automatically (unless `skipDeploys: true`).

### 6. Generate a public domain

```
Tool: generate-domain
Params:
  workspacePath: <repo root>
```

Returns a `*.up.railway.app` URL. This is the public endpoint for the MCP server.

### 7. Verify deployment

1. **Health check:** `curl https://<domain>/health_check` should return `{"status":"ok"}`
2. **MCP handshake:** POST to `https://<domain>/mcp` with:
   - Header: `Accept: application/json, text/event-stream`
   - Body: `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}`
   - Should return `serverInfo` with the server name

## Gotchas

- **Service must exist before setting variables.** Deploy first (even if it fails), then set vars. The var update triggers a redeploy.
- **Railway sets PORT dynamically.** The Dockerfile and server.py read `PORT` from env — don't hardcode it.
- **Accept header required.** MCP streamable-http requires `Accept: application/json, text/event-stream` or you get a 406.
- **No GumstackHost needed.** FastMCP's built-in `streamable-http` transport works directly with Railway.
