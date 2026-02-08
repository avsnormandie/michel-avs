#!/usr/bin/env python3
"""MCP Server for AVS Brain"""

import json
import sys
import subprocess
import os
from pathlib import Path

SKILL_DIR = Path(__file__).parent
SCRIPTS_DIR = SKILL_DIR / "scripts"

def log_debug(msg):
    print(msg, file=sys.stderr, flush=True)

def run_brain_command(cmd: list) -> dict:
    try:
        env = os.environ.copy()
        result = subprocess.run(
            ["python3"] + cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=SCRIPTS_DIR,
            env=env
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {"error": result.stderr or "Command failed"}
    except json.JSONDecodeError:
        return {"output": result.stdout}
    except Exception as e:
        return {"error": str(e)}

TOOLS = [
    {
        "name": "brain_stats",
        "description": "Affiche les statistiques du cerveau de Michel (nombre de memoires, types, sync AVS)",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "brain_search",
        "description": "Recherche dans la memoire de Michel (recherche hybride FTS + embeddings)",
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
        "description": "Memorise une nouvelle information dans le cerveau",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre court"},
                "content": {"type": "string", "description": "Contenu a memoriser"},
                "type": {"type": "string", "enum": ["memory", "concept", "decision", "person", "company", "product"], "default": "memory"},
                "importance": {"type": "integer", "minimum": 0, "maximum": 100, "default": 50}
            },
            "required": ["title", "content"]
        }
    }
]

def handle_request(request: dict) -> dict:
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "avs-brain", "version": "1.0.0"}
            }
        }
    
    elif method == "notifications/initialized":
        return None  # No response needed for notifications
    
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        }
    
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        if tool_name == "brain_stats":
            result = run_brain_command(["brain.py", "stats"])
        elif tool_name == "brain_search":
            query = args.get("query", "")
            result = run_brain_command(["brain.py", "search", query, "--limit", "5"])
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
        
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}]
            }
        }
    
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    
    return {"jsonrpc": "2.0", "id": req_id, "result": {}}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response:  # Don't send response for notifications
                print(json.dumps(response), flush=True)
        except json.JSONDecodeError as e:
            log_debug(f"JSON error: {e}")
        except Exception as e:
            log_debug(f"Error: {e}")
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}), flush=True)

if __name__ == "__main__":
    main()
