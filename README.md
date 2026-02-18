# arista-mcp-server

Arista EOS switch management via eAPI

## Install

```bash
pip install arista-mcp-server
# or
uvx arista-mcp-server
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

See `--help` for additional options:

```bash
arista-mcp-server --help
```

## Development

```bash
git clone https://github.com/clearminds/arista-mcp-server.git
cd arista-mcp-server
uv sync
uv run arista-mcp-server
```

## License

MIT
