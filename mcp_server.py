#!/usr/bin/env python3
"""Standalone MCP Server entry point.

Run the Gemen tools as an MCP server for external clients like Claude Desktop.

Usage:
    # stdio transport (for Claude Desktop, etc.)
    python mcp_server.py

    # HTTP transport (for web clients)
    python mcp_server.py --transport http --port 8080

    # SSE transport (Server-Sent Events)
    python mcp_server.py --transport sse --port 8080

Environment variables:
    MCP_TRANSPORT: Transport protocol (stdio/sse/http), default: stdio
    MCP_HOST: Host for HTTP transports, default: 0.0.0.0
    MCP_PORT: Port for HTTP transports, default: 8000
"""

import argparse
import logging
import os
import sys

# Ensure the project root is in path
sys.path.insert(0, ".")

from tools import run_mcp_server


def main():
    parser = argparse.ArgumentParser(
        description="Run Gemen Tools as MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # For Claude Desktop (stdio)
    python mcp_server.py

    # For web access
    python mcp_server.py --transport http --port 8080

    # Then connect with MCP Inspector:
    # npx @modelcontextprotocol/inspector http://localhost:8080/mcp
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport protocol (default: stdio, env: MCP_TRANSPORT)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="Host for HTTP transports (default: 0.0.0.0, env: MCP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8000")),
        help="Port for HTTP transports (default: 8000, env: MCP_PORT)",
    )

    args = parser.parse_args()

    # Configure logging for HTTP mode (stdio mode should stay quiet)
    if args.transport != "stdio":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        print(f"Starting MCP server on {args.host}:{args.port} ({args.transport})")

    run_mcp_server(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
