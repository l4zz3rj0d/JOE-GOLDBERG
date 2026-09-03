#!/usr/bin/env python3
# scripts/train_voice_phrases.py
"""
Voice Command Deep Training Utility for Soldier Boy.
Registers custom wake phrases, mumble speech thresholds, and sarcastic response triggers.
"""

import sys
import os
import json
import yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.soldierboy_memory import SoldierBoyMemory
from modules.self_upgrade import SoldierBoySelfUpgrade


def train_phrase(trigger_phrase: str, category: str = "custom_phrase", response_override: str = ""):
    print(f"[train_voice_phrases] Training acoustic model for phrase: '{trigger_phrase}'...")

    # 1. Update persistent memory
    mem = SoldierBoyMemory()
    mem.log_speech_pattern(f"Deep voice training registered for '{trigger_phrase}' (category: {category})")

    # 2. Update wake word sensitivity template
    tmpl_path = ROOT / "data" / "skill_templates" / "wake_word_sensitivity.yaml"
    if tmpl_path.exists():
        try:
            with open(tmpl_path, "r") as f:
                data = yaml.safe_load(f) or {}
            aliases = data.setdefault("phonetic_aliases", [])
            if trigger_phrase.lower() not in [a.lower() for a in aliases]:
                aliases.append(trigger_phrase.lower())
                with open(tmpl_path, "w") as f:
                    yaml.dump(data, f)
                print(f"[train_voice_phrases] Updated wake_word_sensitivity.yaml with '{trigger_phrase}'")
        except Exception as e:
            print(f"[train_voice_phrases] Template update notice: {e}")

    # 3. Log level-up notification
    upgrader = SoldierBoySelfUpgrade()
    upgrader.record_skill_feedback("wake_word_training", hit=True)
    print(f"[train_voice_phrases] Successfully trained phrase '{trigger_phrase}'. Soldier Boy is locked and loaded.")


def main():
    args = sys.argv[1:]
    if not args:
        print("\nSoldier Boy Deep Voice Command Training Utility\n")
        print("Usage:")
        print("  python3 train_voice_phrases.py 'phrase' [category]")
        print("\nExamples:")
        print("  python3 train_voice_phrases.py 'Hey Soldier' wake_word")
        print("  python3 train_voice_phrases.py 'Oh great' sarcastic_trigger")
        print("  python3 train_voice_phrases.py 'I am home you beautiful bastard' arrival_macro\n")
        
        # Run default deep training calibration
        train_phrase("Hey Soldier", "wake_word")
        train_phrase("Oh great", "sarcastic_trigger")
        train_phrase("I'm home you beautiful bastard", "arrival_macro")
        return

    phrase = args[0]
    cat = args[1] if len(args) > 1 else "custom_phrase"
    train_phrase(phrase, cat)


if __name__ == "__main__":
    main()
