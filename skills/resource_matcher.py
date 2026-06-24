import json
import os
from typing import Dict, Any, Tuple

INVENTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "inventory.json")

def load_inventory() -> Dict[str, int]:
    if not os.path.exists(INVENTORY_FILE):
        return {}
    with open(INVENTORY_FILE, "r") as f:
        return json.load(f)

def save_inventory(inventory: Dict[str, int]):
    with open(INVENTORY_FILE, "w") as f:
        json.dump(inventory, f, indent=4)

def allocate_resources(needed_resources: Dict[str, int]) -> Tuple[bool, Dict[str, int], str]:
    """
    Skill: Resource Matcher
    Checks inventory for needed resources and allocates them if possible.
    Returns (success, allocated, message)
    """
    inventory = load_inventory()
    allocated = {}
    missing = []

    for item, qty in needed_resources.items():
        if item in inventory and inventory[item] >= qty:
            allocated[item] = qty
        else:
            available = inventory.get(item, 0)
            allocated[item] = available
            missing.append(f"{item} (need {qty}, have {available})")

    # If we want to strictly fail when missing items, we can return False.
    # But in a crisis, we allocate what we can.
    
    # Actually deduct from inventory (but wait for HITL approval in real life, here we just do it for demo)
    for item, qty in allocated.items():
        inventory[item] -= qty
    
    save_inventory(inventory)

    if missing:
        return False, allocated, f"Partial allocation. Missing: {', '.join(missing)}"
    
    return True, allocated, "All resources successfully allocated."
