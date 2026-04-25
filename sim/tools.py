from __future__ import annotations


TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "move",
        "description": "Move toward a target tile, agent, or named location.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Examples: 10,12, Mira, my_house, nearest_forest, nearest_farm"},
                "thought": {"type": "string"},
            },
            "required": ["target", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "speak",
        "description": "Say something out loud to a nearby villager or broadcast to everyone nearby within earshot.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "target": {"type": "string", "description": "Another villager name or everyone"},
                "thought": {"type": "string"},
            },
            "required": ["message", "target", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "give_gift",
        "description": "Give an item as a present to an adjacent villager. Gifts can warm relationships, create obligation, and work especially well during house visits.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_agent": {"type": "string"},
                "item": {"type": "string", "enum": ["wood", "wheat", "berries", "fish", "flowers", "meal"]},
                "quantity": {"type": "integer"},
                "message": {"type": "string"},
                "thought": {"type": "string"},
            },
            "required": ["target_agent", "item", "quantity", "message", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "propose_alliance",
        "description": "Ask an adjacent villager to form a closer alliance or partnership. The practical upside is not guaranteed, but it may shape future cooperation.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_agent": {"type": "string"},
                "message": {"type": "string"},
                "thought": {"type": "string"},
            },
            "required": ["target_agent", "message", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "farm",
        "description": "Plant or harvest wheat on an adjacent farm tile.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["plant", "harvest"]},
                "tile_position": {"type": "string", "description": "x,y"},
                "thought": {"type": "string"},
            },
            "required": ["action", "tile_position", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "light_fire",
        "description": "Burn some wood at your own house so the chimney stays lit and nighttime recovery at home becomes better for a while.",
        "parameters": {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
            },
            "required": ["thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "chop_wood",
        "description": "Harvest wood from an adjacent forest tile.",
        "parameters": {
            "type": "object",
            "properties": {
                "tile_position": {"type": "string", "description": "x,y"},
                "thought": {"type": "string"},
            },
            "required": ["tile_position", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "forage",
        "description": "Gather berries from an adjacent berry grove tile for quick food and energy.",
        "parameters": {
            "type": "object",
            "properties": {
                "tile_position": {"type": "string", "description": "x,y"},
                "thought": {"type": "string"},
            },
            "required": ["tile_position", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "fish",
        "description": "Catch fish from an adjacent pond tile for food and trade.",
        "parameters": {
            "type": "object",
            "properties": {
                "tile_position": {"type": "string", "description": "x,y"},
                "thought": {"type": "string"},
            },
            "required": ["tile_position", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "gather_flowers",
        "description": "Gather flowers from an adjacent flower garden tile to raise morale and collect a tradeable gift.",
        "parameters": {
            "type": "object",
            "properties": {
                "tile_position": {"type": "string", "description": "x,y"},
                "thought": {"type": "string"},
            },
            "required": ["tile_position", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "cook_meal",
        "description": "Cook a communal meal at the hearth using wheat or berries plus wood.",
        "parameters": {
            "type": "object",
            "properties": {
                "ingredient": {"type": "string", "enum": ["wheat", "berries", "fish"]},
                "quantity": {"type": "integer"},
                "thought": {"type": "string"},
            },
            "required": ["ingredient", "quantity", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "sleep",
        "description": "Sleep inside your own house to restore energy.",
        "parameters": {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
            },
            "required": ["thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "rest",
        "description": "Take a short rest anywhere to recover a little energy.",
        "parameters": {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
            },
            "required": ["thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "offer_trade",
        "description": "Offer a trade to an adjacent villager.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_agent": {"type": "string"},
                "offer": {
                    "type": "object",
                    "properties": {
                        "wood": {"type": "integer"},
                        "wheat": {"type": "integer"},
                        "berries": {"type": "integer"},
                        "fish": {"type": "integer"},
                        "flowers": {"type": "integer"},
                        "meal": {"type": "integer"},
                    },
                    "required": ["wood", "wheat", "berries", "fish", "flowers", "meal"],
                    "additionalProperties": False,
                },
                "request": {
                    "type": "object",
                    "properties": {
                        "wood": {"type": "integer"},
                        "wheat": {"type": "integer"},
                        "berries": {"type": "integer"},
                        "fish": {"type": "integer"},
                        "flowers": {"type": "integer"},
                        "meal": {"type": "integer"},
                    },
                    "required": ["wood", "wheat", "berries", "fish", "flowers", "meal"],
                    "additionalProperties": False,
                },
                "message": {"type": "string"},
                "thought": {"type": "string"},
            },
            "required": ["target_agent", "offer", "request", "message", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "contribute_project",
        "description": "Contribute wood or wheat to a public village project when you are at or adjacent to its site.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Examples: granary, wood_shed"},
                "contribution": {
                    "type": "object",
                    "properties": {
                        "wood": {"type": "integer"},
                        "wheat": {"type": "integer"},
                    },
                    "required": ["wood", "wheat"],
                    "additionalProperties": False,
                },
                "thought": {"type": "string"},
            },
            "required": ["project_name", "contribution", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "accept_trade",
        "description": "Accept a pending trade offer sent to you.",
        "parameters": {
            "type": "object",
            "properties": {
                "trade_id": {"type": "string"},
                "thought": {"type": "string"},
            },
            "required": ["trade_id", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "accept_alliance",
        "description": "Accept a pending alliance proposal sent to you.",
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
                "thought": {"type": "string"},
            },
            "required": ["proposal_id", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "reject_alliance",
        "description": "Reject a pending alliance proposal sent to you.",
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
                "reason": {"type": "string"},
                "thought": {"type": "string"},
            },
            "required": ["proposal_id", "reason", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "reject_trade",
        "description": "Reject a pending trade offer sent to you.",
        "parameters": {
            "type": "object",
            "properties": {
                "trade_id": {"type": "string"},
                "reason": {"type": "string"},
                "thought": {"type": "string"},
            },
            "required": ["trade_id", "reason", "thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "wait",
        "description": "Do nothing for this tick.",
        "parameters": {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
            },
            "required": ["thought"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]
