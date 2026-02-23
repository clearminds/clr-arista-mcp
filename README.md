# clr-arista-mcp

Arista EOS switch management via eAPI

## Install

```bash
pip install clr-arista-mcp
# or
uvx clr-arista-mcp
```

## Configuration

**Preferred:** Configuration file at `~/.config/arista/credentials.json` (chmod 600):

```json
{
  "username": "admin",
  "password": "your-password",
  "ssh_key": "/path/to/id_rsa"
}
```

**Note:** Either password or ssh_key is required, not both.

**Alternative:** Environment variables are also supported:

| Variable | Description | Example |
|----------|-------------|---------|
| `ARISTA_USERNAME` | Arista username | `admin` |
| `ARISTA_PASSWORD` | Arista password | `your-password` |
| `ARISTA_SSH_KEY` | SSH key path | `/path/to/id_rsa` |

Optional:

| Variable | Description | Default |
|----------|-------------|---------|
| `ARISTA_READ_ONLY` | Run in read-only mode | `false` |
| `ARISTA_TRANSPORT` | Transport protocol (`stdio` or `http`) | `stdio` |
| `ARISTA_LOG_LEVEL` | Log level | `INFO` |

See `--help` for additional options:

```bash
clr-arista-mcp --help
```

## Development

```bash
git clone https://github.com/clearminds/clr-arista-mcp.git
cd clr-arista-mcp
uv sync
uv run clr-arista-mcp
```

## License

MIT
