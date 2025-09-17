#!/usr/bin/env python3
"""
Multi-MCP Server Wrapper
Supports multiple MCP servers including Diagrams and Microsoft Docs
"""

import asyncio
import json
import os
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Multi-MCP Server",
    description="HTTP wrapper for multiple MCP servers (Diagrams + Microsoft Docs)",
    version="1.0.0"
)

class MCPToolRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any]

class MCPServerManager:
    """Manager for multiple MCP servers"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.servers = {}
        self._setup_servers()
    
    def _setup_servers(self):
        """Setup available MCP servers"""
        # Diagram MCP Server
        diagram_server_path = self.base_dir / "mcp_diagrams_server.py"
        if diagram_server_path.exists():
            self.servers['diagrams'] = {
                'path': diagram_server_path,
                'tools': ['validate_component', 'get_component_suggestions', 'generate_diagram']
            }
            logger.info(f"Registered diagram MCP server: {diagram_server_path}")
        
        # Microsoft Docs MCP Server (using the built-in one)
        # This will use the mcp_microsoft_doc tools directly
        self.servers['microsoft_docs'] = {
            'path': None,  # Built-in
            'tools': ['microsoft_docs_search', 'microsoft_docs_fetch']
        }
        logger.info("Registered Microsoft Docs MCP server")
    
    async def call_diagram_server(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call the diagram MCP server"""
        server_path = self.servers['diagrams']['path']
        
        # Create MCP request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": arguments
            }
        }
        
        try:
            # Start MCP server process
            process = await asyncio.create_subprocess_exec(
                "python3",
                str(server_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Send initialization
            init_request = {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-http-client", "version": "1.0.0"}
                }
            }
            
            await process.stdin.write(json.dumps(init_request).encode() + b'\n')
            await process.stdin.write(json.dumps(request).encode() + b'\n')
            await process.stdin.close()
            
            # Read response
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"MCP server failed: {stderr.decode()}")
                raise Exception(f"MCP server error: {stderr.decode()}")
            
            # Parse response (last line should be the result)
            lines = stdout.decode().strip().split('\n')
            for line in reversed(lines):
                try:
                    response = json.loads(line)
                    if 'result' in response:
                        return response['result']
                except json.JSONDecodeError:
                    continue
            
            raise Exception("No valid response from MCP server")
            
        except Exception as e:
            logger.error(f"Error calling diagram MCP server: {e}")
            raise
    
    async def call_microsoft_docs(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call Microsoft Docs MCP tools directly"""
        try:
            if tool == "microsoft_docs_search":
                # Import and call the Microsoft Docs search function
                from mcp_microsoft_doc_microsoft_docs_search import mcp_microsoft_doc_microsoft_docs_search
                
                query = arguments.get("query", "")
                if not query:
                    raise ValueError("Query parameter required for microsoft_docs_search")
                
                # Call the search function
                results = mcp_microsoft_doc_microsoft_docs_search(query=query)
                return {"content": results}
                
            elif tool == "microsoft_docs_fetch":
                from mcp_microsoft_doc_microsoft_docs_fetch import mcp_microsoft_doc_microsoft_docs_fetch
                
                url = arguments.get("url", "")
                if not url:
                    raise ValueError("URL parameter required for microsoft_docs_fetch")
                
                # Call the fetch function
                content = mcp_microsoft_doc_microsoft_docs_fetch(url=url)
                return {"content": content}
                
            else:
                raise ValueError(f"Unknown Microsoft Docs tool: {tool}")
                
        except ImportError as e:
            logger.error(f"Microsoft Docs MCP tools not available: {e}")
            # Fallback to mock response for development
            if tool == "microsoft_docs_search":
                return {
                    "content": [{
                        "title": "Azure Architecture Best Practices (Mock)",
                        "content": "This is a mock response. Microsoft Docs MCP integration needs to be configured.",
                        "contentUrl": "https://learn.microsoft.com/en-us/azure/"
                    }]
                }
            return {"content": "Microsoft Docs MCP integration not fully configured"}
            
        except Exception as e:
            logger.error(f"Error calling Microsoft Docs MCP: {e}")
            raise
    
    async def call_tool(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Route tool call to appropriate MCP server"""
        # Route diagram tools
        if tool in self.servers['diagrams']['tools']:
            return await self.call_diagram_server(tool, arguments)
        
        # Route Microsoft Docs tools
        elif tool in self.servers['microsoft_docs']['tools']:
            return await self.call_microsoft_docs(tool, arguments)
        
        else:
            raise ValueError(f"Unknown tool: {tool}")

# Global manager instance
mcp_manager = MCPServerManager()

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "Multi-MCP Server running",
        "servers": list(mcp_manager.servers.keys()),
        "tools": {
            server: config['tools'] 
            for server, config in mcp_manager.servers.items()
        }
    }

@app.get("/health")
async def health_check():
    """Health check for the multi-MCP service"""
    return {"status": "healthy", "servers": len(mcp_manager.servers)}

@app.post("/mcp/call_tool")
async def call_mcp_tool(request: MCPToolRequest):
    """Call an MCP tool through the appropriate server"""
    try:
        logger.info(f"Calling MCP tool: {request.tool} with args: {request.arguments}")
        
        result = await mcp_manager.call_tool(request.tool, request.arguments)
        
        logger.info(f"MCP tool {request.tool} completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"MCP tool call failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/mcp/tools")
async def list_tools():
    """List all available MCP tools"""
    all_tools = []
    for server_name, config in mcp_manager.servers.items():
        for tool in config['tools']:
            all_tools.append({
                "tool": tool,
                "server": server_name
            })
    return {"tools": all_tools}


@app.post("/mcp/tools/call")
async def call_tool_legacy(request: Dict[str, Any]):
    """Call an MCP tool (legacy endpoint for compatibility)"""
    try:
        tool_name = request.get("name")
        arguments = request.get("arguments", {})
        
        if not tool_name:
            raise ValueError("Tool name is required")
        
        logger.info(f"Legacy MCP tool call: {tool_name} with args: "
                    f"{arguments}")
        
        result = await mcp_manager.call_tool(tool_name, arguments)
        
        logger.info(f"Legacy MCP tool {tool_name} completed successfully")
        response_data = {
            "success": True,
            "result": {
                "result": {
                    "content": [{"text": json.dumps(result)}]
                }
            }
        }
        return response_data
        
    except Exception as e:
        logger.error(f"Legacy MCP tool call failed: {e}")
        return {"success": False, "error": str(e)}


@app.post("/mcp/generate-diagram")
async def generate_diagram(request: Dict[str, Any]):
    """Generate a diagram using MCP diagram tools"""
    try:
        # Extract parameters
        architecture_description = request.get("architecture_description", "")
        diagram_code = request.get("diagram_code", "")
        
        if not architecture_description and not diagram_code:
            raise ValueError("Either architecture_description or "
                             "diagram_code is required")
        
        logger.info("Generating diagram for: "
                    f"{architecture_description[:100]}...")
        
        # If we have an architecture description, call generate_diagram
        # tool directly
        if architecture_description:
            result = await mcp_manager.call_tool("generate_diagram", {
                "description": architecture_description,
                "provider": "azure",
                "format": "png"
            })
        else:
            # If we have diagram code, call generate_diagram with the code
            result = await mcp_manager.call_tool("generate_diagram", {
                "code": diagram_code,
                "format": "png"
            })
        
        logger.info("Diagram generation completed")
        response_data = {
            "success": True,
            "result": {
                "result": {
                    "content": [{"text": json.dumps(result)}]
                }
            }
        }
        return response_data
        
    except Exception as e:
        logger.error(f"Diagram generation failed: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)