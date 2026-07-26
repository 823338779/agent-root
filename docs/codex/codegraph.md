# CodeGraph workspace index

Run CodeGraph from the `agent-root` directory so one index covers both Git submodules:

```powershell
codegraph sync .
codegraph status .
```

The root index includes files below both `data-agent/` and `metric-platform/`. Verify their coverage independently when diagnosing an empty or partial result:

```powershell
codegraph files --filter data-agent --format flat
codegraph files --filter metric-platform --format flat
```

For a new checkout with no `.codegraph/` directory, initialize it once from the workspace root:

```powershell
codegraph init .
```

Use `codegraph index .` only for a deliberate full rebuild. A running MCP server or CodeGraph daemon keeps the database open; stop it before rebuilding. Normal source changes need only `codegraph sync .`, and an active watcher usually synchronizes them automatically.
