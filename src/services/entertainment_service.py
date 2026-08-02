from __future__ import annotations

import logging
import random

import flet as ft

logger = logging.getLogger(__name__)

EASTER_EGGS: dict[str, tuple[str, str]] = {
    "Sword of a Thousand Truths": ("Wow! The legendary sword!", ft.Colors.AMBER),
    "Bread of Eternal Life": ("This bread will never spoil!", ft.Colors.GREEN_400),
    "Golden Chicken": ("Cluck cluck! It lays golden eggs!", ft.Colors.ORANGE_ACCENT),
    "Governor's Keycard": ("Access level: OVER 9000!", ft.Colors.PURPLE_ACCENT),
    "Unicorn Meat": ("Tastes like rainbows and sparkles!", ft.Colors.PINK_ACCENT),
}

FUN_SAVE_MESSAGES = [
    "economy_ultimate_final_v3.xml saved!",
    "Another day, another dollar...",
    "Your changes have been preserved for posterity!",
    "The loot gods are pleased!",
    "Saved! Time to test on your server!",
    "Your edits have been blessed by the DayZ gods!",
    "File saved. No zombies were harmed in the process.",
    "Save successful! The helicopter is on its way.",
]

FUN_LUCKY_PHRASES = [
    "The loot gods have spoken!",
    "Chaos reigns supreme!",
    "Fortune favors the bold!",
    "RNGesus has blessed you!",
    "May the odds be ever in your favor!",
    "Embrace the randomness!",
    "Let's spice things up!",
    "Time to get wild!",
]

ACHIEVEMENTS: dict[int, str] = {
    10: "Apprentice Editor",
    50: "Getting Started",
    100: "Dedicated Editor",
    500: "Economy Master",
    1000: "DayZ Legend",
}

CAT_TIPS = [
    "Cats love watching the loot economy simulation",
    "A cat's purr is like a well-balanced spawn rate",
    "Cats always land on their feet, just like persistent items",
    "Meow! Don't forget to save your progress",
    "Catnip is the ultimate rare loot",
    "Every cat deserves a cozy spawn point",
    "Keyboard cats make the best editors",
    "Paws for a moment and check your nominal values",
    "Cats believe the best Nominal is the one that keeps them entertained",
    "A cat's curiosity is like testing different Cost values",
    "Purring means your Restock timer is just right",
    "Cats love watching loot spawn – it's a game of hunt to them",
    "If your cat walks across the keyboard, it's probably adjusting QuantMin",
    "Meow! Remember to check the 'Map' flag for outdoor spawns",
    "Cats prefer 'Hoarder' items because they like to collect things",
    "A catnap is a good time to let the economy settle and stabilise",
    "Cats agree: the 'Food' category should always have high spawn rates",
    "Staring at the screen? Your cat is calculating the perfect Lifetime",
    "Cats don't like empty containers – so check your Min values",
    "Every cat knows that 'Cost = -1' means an invisible mouse",
    "Purr‑haps you should add more Usage values for variety",
    "Cats are masters of balance – they know when to tweak Nominal",
    "Don't forget to save before your cat decides to 'help' you type",
    "Meow, meow, meow! Meow, meow!",
]


class EntertainmentService:
    def __init__(self) -> None:
        self.edit_stats: dict[str, int] = {}
        self.total_edits: int = 0
        self._unlocked_achievements: set[int] = set()
        self.cat_mode: bool = False
        self.terminal_mode: bool = False
        self.fun_save_messages: bool = False
        self.show_meme_on_save: bool = False
        self.funny_enabled: bool = False
        self._achievement_dirty: bool = False

    def record_edit(self, field_key: str) -> None:
        self.edit_stats[field_key] = self.edit_stats.get(field_key, 0) + 1
        self.total_edits += 1

    def check_easter_egg(self, name: str) -> tuple[str, str] | None:
        return EASTER_EGGS.get(name)

    def check_achievements(self) -> int | None:
        for threshold in sorted(ACHIEVEMENTS):
            if (
                self.total_edits >= threshold
                and threshold not in self._unlocked_achievements
            ):
                self._unlocked_achievements.add(threshold)
                self._achievement_dirty = True
                return threshold
        return None

    def get_achievement_name(self, threshold: int) -> str | None:
        return ACHIEVEMENTS.get(threshold)

    def get_fun_save_message(self) -> str:
        return random.choice(FUN_SAVE_MESSAGES)

    def get_lucky_phrase(self) -> str:
        return random.choice(FUN_LUCKY_PHRASES)

    def get_stats_text(self) -> str:
        if not self.edit_stats:
            return "No edits recorded yet!"
        max_count = max(self.edit_stats.values())
        lines = ["═══ EDIT STATS ═══\n"]
        for key, count in sorted(self.edit_stats.items(), key=lambda x: -x[1]):
            bar_len = int((count / max_count) * 20) if max_count > 0 else 0
            bar = "█" * bar_len
            lines.append(f"{key:12s} {bar:20s} {count}")
        lines.append(f"\nTotal edits: {self.total_edits}")
        return "\n".join(lines)

    def get_cat_tip(self, idx: int) -> str:
        return CAT_TIPS[idx % len(CAT_TIPS)]

    @property
    def unlocked_achievements(self) -> set[int]:
        return self._unlocked_achievements

    @property
    def achievements_str(self) -> str:
        return ",".join(str(t) for t in sorted(self._unlocked_achievements))

    @achievements_str.setter
    def achievements_str(self, value: str) -> None:
        if value:
            try:
                self._unlocked_achievements = set(
                    int(x) for x in value.split(",") if x.strip()
                )
            except (ValueError, TypeError):
                pass
