#!/usr/bin/env python3
"""
Brain Claude - Use Claude Code CLI instead of Anthropic API

Usage:
    brain_claude.py ask QUESTION
    brain_claude.py --system SYSTEM_PROMPT --prompt PROMPT [--model MODEL]

Uses Claude Code subscription (Max) instead of paying per-token API.
"""

import argparse
import json
import subprocess
import sys
import os
from pathlib import Path

def run_claude(prompt: str, system: str = None, model: str = "sonnet") -> dict:
    """
    Run Claude Code CLI and return the response.

    Args:
        prompt: The prompt to send to Claude
        system: Optional system prompt
        model: Model to use (sonnet, opus, haiku)

    Returns:
        dict with 'success', 'response' or 'error'
    """
    try:
        # Build command
        cmd = ["claude", "-p", prompt, "--print"]

        if system:
            cmd.extend(["--system", system])

        if model and model != "sonnet":
            cmd.extend(["--model", model])

        # Run Claude Code
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )

        if result.returncode == 0:
            return {
                "success": True,
                "response": result.stdout.strip()
            }
        else:
            return {
                "success": False,
                "error": result.stderr.strip() or f"Exit code: {result.returncode}"
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Timeout: Claude took too long to respond"
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "Claude Code CLI not found. Make sure it's installed: npm install -g @anthropic-ai/claude-code"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def cmd_ask(args):
    """Simple question to Claude"""
    result = run_claude(args.question)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("success") else 1


def cmd_prompt(args):
    """Custom prompt with optional system prompt"""
    result = run_claude(
        prompt=args.prompt,
        system=args.system,
        model=args.model
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("success") else 1


def main():
    parser = argparse.ArgumentParser(description='Brain Claude - Claude Code CLI wrapper')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # ask - simple question
    p_ask = subparsers.add_parser('ask', help='Ask a simple question')
    p_ask.add_argument('question', help='Question to ask Claude')

    # prompt - custom prompt with system
    p_prompt = subparsers.add_parser('prompt', help='Custom prompt with system')
    p_prompt.add_argument('--system', '-s', help='System prompt')
    p_prompt.add_argument('--prompt', '-p', required=True, help='User prompt')
    p_prompt.add_argument('--model', '-m', default='sonnet',
                         choices=['sonnet', 'opus', 'haiku'],
                         help='Model to use (default: sonnet)')

    args = parser.parse_args()

    if not args.command:
        # If no subcommand, treat all args as a question
        if len(sys.argv) > 1:
            question = ' '.join(sys.argv[1:])
            result = run_claude(question)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get("success") else 1
        else:
            parser.print_help()
            return 1

    commands = {
        'ask': cmd_ask,
        'prompt': cmd_prompt
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
