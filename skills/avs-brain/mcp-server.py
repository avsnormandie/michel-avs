#!/usr/bin/env python3
"""MCP Server for AVS Brain - exposes brain tools to Claude Code"""

import json
import sys
import subprocess
from pathlib import Path

SKILL_DIR = Path(__file__).parent
SCRIPTS_DIR = SKILL_DIR / "scripts"

def run_brain_command(cmd: list) -> dict:
    try:
        result = subprocess.run(
            ["python3"] + cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=SCRIPTS_DIR
        )
        return json.loads(result.stdout) if result.returncode == 0 else {"error": result.stderr}
    except Exception as e:
        return {"error": str(e)}

def handle_request(request: dict) -> dict:
    method = request.get("method")
    params = request.get("params", {})
    
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "avs-brain", "version": "1.0.0"}
        }
    
    elif method == "tools/list":
        return {
            "tools": [
                {
                    "name": "brain_stats",
                    "description": "Statistiques du cerveau de Michel",
                    "inputSchema": {"type": "object", "properties": {}}
                },
                {
                    "name": "brain_search",
                    "description": "Rechercher dans la memoire de Michel",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Termes de recherche"}
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "brain_remember",
                    "description": "Memoriser une information",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "type": {"type": "string", "default": "memory"},
                            "importance": {"type": "integer", "default": 50}
                        },
                        "required": ["title", "content"]
                    }
                }
            ]
        }
    
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        if tool_name == "brain_stats":
            result = run_brain_command(["brain.py", "stats"])
        elif tool_name == "brain_search":
            result = run_brain_command(["brain.py", "search", args.get("query", ""), "--limit", "5"])
        elif tool_name == "brain_remember":
            result = run_brain_command([
                "brain.py", "remember",
                "--title", args.get("title", ""),
                "--content", args.get("content", ""),
                "--type", args.get("type", "memory"),
                "--importance", str(args.get("importance", 50))
            ])
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}]}
    
    return {}

def main():
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle_request(request)
            response["jsonrpc"] = "2.0"
            response["id"] = request.get("id")
            print(json.dumps(response), flush=True)
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "error": {"message": str(e)}}), flush=True)

if __name__ == "__main__":
    main()
