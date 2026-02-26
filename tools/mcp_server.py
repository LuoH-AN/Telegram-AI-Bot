"""MCP Server adapter — exposes existing tools as MCP tools.

This allows the same tools to be called via:
1. Telegram Bot: using ToolRegistry (existing method)
2. Other platforms (Claude Desktop, etc.): using MCP protocol

Usage:
    # Run as MCP server (stdio transport)
    python -m tools.mcp_server

    # Or run with HTTP transport
    python -m tools.mcp_server --transport http --port 8080

Authentication:
    Set MCP_API_KEY environment variable to require API key authentication.
    Clients must include: Authorization: Bearer <api_key>
    Or: X-API-Key: <api_key>
"""

import argparse
import asyncio
import inspect
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .registry import registry, BaseTool

logger = logging.getLogger(__name__)

# Default user ID for MCP calls (no per-user context in MCP)
MCP_DEFAULT_USER_ID = 0

# API Key for authentication (optional, set via environment variable)
MCP_API_KEY = os.getenv("MCP_API_KEY", "").strip()


def create_mcp_server(name: str = "Gemen Tools", tool_filter: str | None = None) -> FastMCP:
    """Create an MCP server that wraps registered tools.

    Args:
        name: Server name shown to MCP clients
        tool_filter: Optional comma-separated list of tool names to include.
                     If None, all tools are included.

    Returns:
        FastMCP server instance with tools registered
    """
    # Transport security:
    # - Localhost mode keeps FastMCP's strict DNS rebinding defaults.
    # - Reverse-proxy/public deployments can configure allowlists via env.
    # - If allowlists are not provided for non-localhost hosts, disable host/origin
    #   checks to avoid false positives behind platforms like Hugging Face Spaces.
    mcp_host = os.getenv("MCP_HOST", "0.0.0.0").strip() or "0.0.0.0"
    allowed_hosts_env = os.getenv("MCP_ALLOWED_HOSTS", "").strip()
    allowed_origins_env = os.getenv("MCP_ALLOWED_ORIGINS", "").strip()

    transport_security: TransportSecuritySettings | None = None
    if allowed_hosts_env or allowed_origins_env:
        allowed_hosts = [h.strip() for h in allowed_hosts_env.split(",") if h.strip()]
        allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        )
    elif mcp_host not in ("127.0.0.1", "localhost", "::1"):
        transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    mcp = FastMCP(
        name,
        json_response=True,
        host=mcp_host,
        transport_security=transport_security,
    )

    # Parse tool filter
    allowed_tools = None
    if tool_filter:
        allowed_tools = {t.strip().lower() for t in tool_filter.split(",") if t.strip()}

    # Iterate all registered tools and wrap them
    for tool in registry._tools:
        for defn in tool.definitions():
            func_def = defn.get("function", {})
            tool_name = func_def.get("name", "")
            if allowed_tools and tool_name.lower() not in allowed_tools:
                continue
            _register_tool_definition(mcp, tool, defn)

    return mcp


def _register_tool_definition(mcp: FastMCP, tool: BaseTool, defn: dict) -> None:
    """Register a single tool definition to the MCP server."""
    func_def = defn.get("function", {})
    tool_name = func_def.get("name")
    if not tool_name:
        return

    description = func_def.get("description", "")
    parameters = func_def.get("parameters", {})
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))

    _create_mcp_tool_wrapper(mcp, tool, tool_name, description, properties, required)


def _create_mcp_tool_wrapper(
    mcp: FastMCP,
    tool: BaseTool,
    tool_name: str,
    description: str,
    properties: dict,
    required: set,
) -> None:
    """Create and register an MCP tool wrapper for a specific tool function."""

    # Build a dynamic function with proper signature
    # MCP uses type hints to generate schemas, so we need to annotate params
    param_names = list(properties.keys())

    # Create parameter annotations string
    params_code = []
    defaults_code = []
    for pname in param_names:
        pschema = properties.get(pname, {})
        ptype = pschema.get("type", "string")
        pdesc = pschema.get("description", "")

        # Map JSON schema types to Python types
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list",
            "object": "dict",
        }
        py_type = type_map.get(ptype, "Any")

        if pname in required:
            params_code.append(f"{pname}: {py_type}")
        else:
            # Has default value
            default_val = pschema.get("default")
            if default_val is not None:
                if isinstance(default_val, str):
                    defaults_code.append(f'{pname}: {py_type} = "{default_val}"')
                else:
                    defaults_code.append(f"{pname}: {py_type} = {default_val}")
            else:
                defaults_code.append(f"{pname}: {py_type} | None = None")

    all_params = params_code + defaults_code
    params_str = ", ".join(all_params) if all_params else ""

    # Create the wrapper function dynamically
    exec_code = f'''
async def _mcp_wrapper({params_str}) -> str:
    """{description}"""
    args = {{{', '.join(f'"{p}": {p}' for p in param_names)}}}
    # Filter out None values for optional params
    args = {{k: v for k, v in args.items() if v is not None}}

    # Execute the tool (BaseTool.execute is sync, so we run it in executor)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        tool.execute,
        MCP_DEFAULT_USER_ID,
        tool_name,
        args
    )
    return result if result is not None else "OK"
'''

    # Create a new namespace for execution
    ns = {
        "asyncio": asyncio,
        "tool": tool,
        "tool_name": tool_name,
        "MCP_DEFAULT_USER_ID": MCP_DEFAULT_USER_ID,
        "Any": Any,
    }
    exec(exec_code, ns)
    wrapper_func = ns["_mcp_wrapper"]

    # Set function name for better debugging
    wrapper_func.__name__ = tool_name
    wrapper_func.__qualname__ = tool_name

    # Register with MCP
    mcp.tool()(wrapper_func)


# Server instance (lazy initialization)
_mcp_server: FastMCP | None = None
# Per-tool server instances
_tool_servers: dict[str, FastMCP] = {}


def get_mcp_server() -> FastMCP:
    """Get or create the main MCP server instance (all tools)."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = create_mcp_server()
    return _mcp_server


def get_tool_mcp_server(tool_name: str) -> FastMCP:
    """Get or create an MCP server for a specific tool.

    Args:
        tool_name: Name of the tool (e.g., 'web_search', 'shell_exec')

    Returns:
        FastMCP server with only the specified tool
    """
    if tool_name not in _tool_servers:
        _tool_servers[tool_name] = create_mcp_server(
            name=f"Gemen - {tool_name}",
            tool_filter=tool_name
        )
    return _tool_servers[tool_name]


def run_mcp_server(transport: str = "stdio", host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the MCP server.

    Args:
        transport: "stdio", "sse", or "streamable-http"
        host: Host for HTTP transports
        port: Port for HTTP transports
    """
    mcp = get_mcp_server()

    # FastMCP API compatibility:
    # - Older versions: run(transport, host=..., port=...)
    # - Newer versions: run(transport, mount_path=None), host/port live in mcp.settings
    run_params = inspect.signature(mcp.run).parameters
    supports_host_port = "host" in run_params and "port" in run_params

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        if supports_host_port:
            mcp.run(transport="sse", host=host, port=port)
        else:
            mcp.settings.host = host
            mcp.settings.port = port
            mcp.run(transport="sse")
    elif transport == "http" or transport == "streamable-http":
        if supports_host_port:
            mcp.run(transport="streamable-http", host=host, port=port)
        else:
            mcp.settings.host = host
            mcp.settings.port = port
            mcp.run(transport="streamable-http")
    else:
        raise ValueError(f"Unknown transport: {transport}")


def mount_mcp_to_app(app, require_auth: bool = True):
    """Mount MCP server to an existing FastAPI app (streamable-http transport).

    This allows MCP to share the same port with your existing web app.

    Args:
        app: FastAPI application instance
        require_auth: Whether to require API key authentication (default: True if MCP_API_KEY is set)

    Endpoints created:
        - /mcp           → All tools (main MCP server)
        - /web_search    → Only web_search tool
        - /shell_exec    → Only shell_exec tool
        - etc.

    Example:
        from fastapi import FastAPI
        from tools import mount_mcp_to_app

        app = FastAPI()
        mount_mcp_to_app(app)

        # MCP endpoint: http://localhost:8080/mcp
        # Tool-specific: http://localhost:8080/web_search/mcp
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    # Determine if auth is required
    if require_auth and not MCP_API_KEY:
        require_auth = False
        logger.warning("MCP_API_KEY not set, authentication disabled")

    # Authentication middleware for MCP endpoints
    class MCPAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Only check auth for MCP-related paths
            if require_auth and "/mcp" in request.url.path:
                # Check Authorization: Bearer <token>
                auth_header = request.headers.get("authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
                else:
                    # Check X-API-Key header
                    token = request.headers.get("x-api-key", "")

                if token != MCP_API_KEY:
                    return JSONResponse(
                        {"error": "Unauthorized", "message": "Invalid or missing API key"},
                        status_code=401,
                    )

            return await call_next(request)

    # Add auth middleware
    if require_auth:
        app.add_middleware(MCPAuthMiddleware)
        logger.info("MCP authentication enabled (API key required)")

    # Mounted Starlette sub-app lifespans are not always entered by parent app
    # (depends on Starlette/FastAPI behavior/version). Newer MCP versions require
    # session_manager.run() to be entered before handling requests. We manage
    # these context managers from the parent app startup/shutdown.
    session_manager_contexts = []

    def _register_session_manager(mcp_server: FastMCP, name: str) -> None:
        try:
            session_manager_contexts.append(mcp_server.session_manager.run())
            logger.info("Registered MCP session manager for %s", name)
        except Exception as e:
            logger.warning("Failed to register MCP session manager for %s: %s", name, e)

    # Mount per-tool MCP servers
    # Each tool server has internal /mcp route, mount at /{tool_name}
    mounted_tool_paths = set()
    for tool in registry._tools:
        for defn in tool.definitions():
            tool_name = defn.get("function", {}).get("name")
            if not tool_name or tool_name in mounted_tool_paths:
                continue
            tool_mcp = get_tool_mcp_server(tool_name)
            tool_app = tool_mcp.streamable_http_app()
            _register_session_manager(tool_mcp, tool_name)
            # Mount at /{tool_name}, so /mcp inside becomes /{tool_name}/mcp
            app.mount(f"/{tool_name}", tool_app)
            mounted_tool_paths.add(tool_name)
            logger.info("Tool '%s' MCP at /%s/mcp", tool_name, tool_name)

    # Mount main MCP server (all tools) at root.
    # Keep this mount last so /{tool_name} mounts above are not shadowed.
    # streamable_http_app() internally creates route at /mcp
    mcp = get_mcp_server()
    mcp_http_app = mcp.streamable_http_app()
    _register_session_manager(mcp, "main")
    app.mount("", mcp_http_app)
    logger.info("MCP server mounted at /mcp (streamable-http transport)")

    @app.on_event("startup")
    async def _startup_mcp_session_managers():
        entered = []
        for ctx in session_manager_contexts:
            await ctx.__aenter__()
            entered.append(ctx)
        app.state._mcp_session_manager_contexts = entered

    @app.on_event("shutdown")
    async def _shutdown_mcp_session_managers():
        entered = getattr(app.state, "_mcp_session_manager_contexts", [])
        while entered:
            ctx = entered.pop()
            await ctx.__aexit__(None, None, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Gemen Tools as MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP transports (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transports (default: 8000)",
    )

    args = parser.parse_args()

    # Configure logging for HTTP mode
    if args.transport != "stdio":
        logging.basicConfig(level=logging.INFO)

    run_mcp_server(transport=args.transport, host=args.host, port=args.port)
