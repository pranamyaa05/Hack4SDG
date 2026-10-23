"""Closed question bank and deterministic supported-object checks."""

import re

from backend.contracts import Track

from .models import AnalysisWorkspace

QUESTION_BANK = {
    "difficulty": {
        "prompt": "What is hardest about holding this?",
        "options": [
            {"id": "slipping", "label": "It slips"},
            {"id": "pain", "label": "Gripping hurts"},
            {"id": "cannot_wrap_fingers", "label": "My fingers cannot wrap around it"},
            {"id": "weak_grip", "label": "My grip is weak"},
            {"id": "other", "label": "Something else / not sure"},
        ],
    },
    "material_preference": {
        "prompt": "Which would you rather hold?",
        "options": [
            {"id": "soft", "label": "Soft"},
            {"id": "rigid", "label": "Firm"},
            {"id": "no_preference", "label": "No preference / not sure"},
        ],
    },
    "repair_case": {
        "prompt": "What needs repairing?",
        "options": [
            {
                "id": "missing_pull_visible_holes",
                "label": "Missing drawer pull; both mounting holes are visible",
            },
            {"id": "hidden_mounting", "label": "Hidden clips or threads"},
            {"id": "other", "label": "Something else"},
            {"id": "not_sure", "label": "Not sure"},
        ],
    },
    "surface_condition": {
        "prompt": "Is the drawer face intact around both mounting holes?",
        "options": [
            {"id": "sound", "label": "Yes, intact"},
            {"id": "damaged", "label": "Cracked or damaged"},
            {"id": "not_sure", "label": "Not sure"},
        ],
    },
}


def extract_explicit_difficulty(text: str):
    text = text.lower().replace("?", "'")
    # Negation and multiple difficulties require clarification instead of a guessed priority.
    if re.search(r"\b(no|not|never|don't|doesn't|isn't|without)\b", text):
        return None
    patterns = {
        "slipping": r"\b(slips?|slipping|slippery|drops?)\b",
        "pain": r"\b(hurts?|pain|painful|aches?)\b",
        "cannot_wrap_fingers": r"(can't|cannot|unable to) (wrap|bend|curl)|too thin",
        "weak_grip": r"\bweak (grip|hands?)\b|\bgrip is weak\b",
    }
    matches = [key for key, pattern in patterns.items() if re.search(pattern, text)]
    return matches[0] if len(matches) == 1 else None


def support_decision(track: Track, workspace: AnalysisWorkspace):
    confirmation = workspace.confirmation
    if confirmation is None:
        return {
            "status": "needs_confirmation",
            "reason": "Confirm or correct the object and target component first.",
        }
    if track == Track.ADAPT:
        if (
            confirmation.object_type not in {"spoon", "fork", "knife"}
            or confirmation.component != "handle"
        ):
            return {
                "status": "unsupported",
                "reason": "Adapt currently supports utensil handles only. Food-contact surfaces and other object families are outside this release.",
            }
        if confirmation.handle_intact is not True:
            return {
                "status": "unsupported",
                "reason": "Confirm an intact handle. Cracked or uncertain structural damage needs an in-person assessment.",
            }
    else:
        if (
            confirmation.object_type != "drawer_handle"
            or confirmation.component != "drawer_mounting_holes"
        ):
            return {
                "status": "unsupported",
                "reason": "Repair currently supports replacement drawer pulls with visible mounting holes.",
            }
        if (
            workspace.answers.repair_case is not None
            and workspace.answers.repair_case != "missing_pull_visible_holes"
        ):
            return {
                "status": "unsupported",
                "reason": "Hidden clips, threads, and uncertain mounting cannot be repaired by this workflow.",
            }
        if (
            workspace.answers.surface_condition is not None
            and workspace.answers.surface_condition != "sound"
        ):
            return {
                "status": "unsupported",
                "reason": "The drawer face around the holes must be confirmed intact before designing a replacement pull.",
            }
    required = (
        ("difficulty", "material_preference")
        if track == Track.ADAPT
        else ("repair_case", "surface_condition")
    )
    missing = [key for key in required if getattr(workspace.answers, key) is None]
    if missing:
        return {
            "status": "needs_answers",
            "reason": "Answer the remaining questions before measurement.",
        }
    return {
        "status": "supported",
        "reason": "This object fits the current catalog scope. Measurements and design validation are still required.",
    }


def questions(track: Track, workspace: AnalysisWorkspace):
    if support_decision(track, workspace)["status"] in {
        "needs_confirmation",
        "unsupported",
    }:
        return []
    slots = (
        ("difficulty", "material_preference")
        if track == Track.ADAPT
        else ("repair_case", "surface_condition")
    )
    return [
        dict(id=key, **QUESTION_BANK[key])
        for key in slots
        if getattr(workspace.answers, key) is None
    ]
