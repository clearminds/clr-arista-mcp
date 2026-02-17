# arista-mcp-server

Arista EOS switch management via eAPI

## Install

```bash
pip install arista-mcp-server
# or
uvx arista-mcp-server
```

## Configuration

Configuration via environment variables. See `--help` for all options:

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
