"""MCP tool routes (for editors).

Guarded by require_role("editor") (issue #1); raw exceptions propagate to the
centralized error handlers (issue #9).
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends

from src.agent.big_flavor_agent import BigFlavorAgent
from src.auth import require_role
from src.api.dependencies import get_agent

router = APIRouter()


@router.get("/api/tools/list")
async def list_tools(
    agent: BigFlavorAgent = Depends(get_agent),
    _role: str = Depends(require_role("editor")),
):
    """List all available MCP tools"""
    tools = agent.get_available_tools()
    return {"tools": tools}


@router.post("/api/tools/execute")
async def execute_tool(
    tool_name: str,
    parameters: Dict[str, Any],
    agent: BigFlavorAgent = Depends(get_agent),
    _role: str = Depends(require_role("editor")),
):
    """Execute an MCP tool (editors only)"""
    result = await agent.execute_tool(tool_name, parameters)
    return {"result": result}
