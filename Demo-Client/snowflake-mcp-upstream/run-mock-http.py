"""Boot the upstream Snowflake-Labs MCP server on HTTP, with mocked connect.

Terminal 1 of the demo. Run from inside this directory so that
`mcp_server_snowflake` resolves to the upstream clone next to this file.

    cd snowflake-mcp-upstream
    python run-mock-http.py

Defaults to http://127.0.0.1:9000/mcp -- the URL normal-client.py expects.
"""

import sys
from unittest.mock import MagicMock

import snowflake.connector
snowflake.connector.connect = lambda **kw: MagicMock(name="MockSnowflakeConnection")

import snowflake.core
snowflake.core.Root = lambda conn: MagicMock(name="MockSnowflakeRoot")

# Inject CLI args for the upstream's parse_arguments() to read.
sys.argv = [
    "run-mock-http.py",
    "--transport", "streamable-http",
    "--server-host", "127.0.0.1",
    "--port", "9000",
    "--endpoint", "/mcp",
    "--service-config-file", "services/configuration.yaml",
]

from mcp_server_snowflake.server import main
main()
