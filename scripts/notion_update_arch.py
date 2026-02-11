#!/usr/bin/env python3
"""Build the data payload for Notion Architecture page update."""
import json

with open(".cursor/notion_architecture_content.md") as f:
    new_str = f.read()

data = {
    "page_id": "303f184a-8d3e-807f-aa93-d9cf68341556",
    "command": "replace_content",
    "new_str": new_str,
}

print(json.dumps(data, ensure_ascii=False)[:200])
print("...")
print("new_str length:", len(new_str))
