#!/usr/bin/env python3
"""
update_arns.py
==============
Run this after redeploying any AgentCore agent to automatically sync
the latest ARNs from the .bedrock_agentcore.yaml files into app_agentcore.py.

Usage:
    python update_arns.py
"""

import os
import re
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AGENTCORE_AGENTS_DIR = os.path.join(BASE_DIR, "agentcore_agents")
APP_FILE = os.path.join(BASE_DIR, "app_agentcore.py")

# Maps agent folder name → key used in AGENT_ARNS dict in app_agentcore.py
AGENT_KEY_MAP = {
    "exception_investigator":  "exception_investigator",
    "replenishment_planner":   "replenishment_planner",
    "stockout_sentinel":       "stockout_sentinel",
    "inventory_copilot":       "inventory_copilot",
    "markdown_coach":          "markdown_coach",
    "market_intelligence":     "market_intelligence",
    "pricing_intelligence":    "pricing_intelligence",
    "email_drafter":           "email_drafter",
}


def read_arn_from_yaml(agent_folder: str) -> str | None:
    yaml_path = os.path.join(AGENTCORE_AGENTS_DIR, agent_folder, ".bedrock_agentcore.yaml")
    if not os.path.exists(yaml_path):
        print(f"  ⚠️  No YAML found for {agent_folder}: {yaml_path}")
        return None
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    # Navigate: agents → <agent_name> → bedrock_agentcore → agent_arn
    for agent_name, agent_cfg in data.get("agents", {}).items():
        arn = agent_cfg.get("bedrock_agentcore", {}).get("agent_arn")
        if arn:
            return arn
    print(f"  ⚠️  agent_arn not found in YAML for {agent_folder}")
    return None


def update_app_agentcore(new_arns: dict[str, str]) -> None:
    with open(APP_FILE) as f:
        content = f.read()

    original = content

    for agent_key, new_arn in new_arns.items():
        # Match the line:  "agent_key": "arn:aws:bedrock-agentcore:..."
        pattern = rf'("{agent_key}"\s*:\s*)"arn:aws:bedrock-agentcore:[^"]*"'
        replacement = rf'\1"{new_arn}"'
        content, count = re.subn(pattern, replacement, content)
        if count:
            print(f"  ✅ Updated {agent_key} → {new_arn.split('/')[-1]}")
        else:
            print(f"  ⚠️  Pattern not matched for {agent_key} — check app_agentcore.py manually")

    if content == original:
        print("\nℹ️  No changes made — all ARNs already up to date.")
        return

    with open(APP_FILE, "w") as f:
        f.write(content)
    print(f"\n✅ {APP_FILE} updated.")


def main():
    print("=" * 60)
    print("🔄 Syncing AgentCore ARNs → app_agentcore.py")
    print("=" * 60)

    new_arns = {}
    for folder, key in AGENT_KEY_MAP.items():
        print(f"\n📂 {folder}")
        arn = read_arn_from_yaml(folder)
        if arn:
            new_arns[key] = arn
            print(f"     ARN: {arn.split('/')[-1]}")

    if not new_arns:
        print("\n❌ No ARNs found — nothing to update.")
        return

    print(f"\n📝 Updating {APP_FILE} ...")
    update_app_agentcore(new_arns)
    print("\n🎉 Done! Restart app_agentcore.py to pick up the new ARNs.")


if __name__ == "__main__":
    main()
