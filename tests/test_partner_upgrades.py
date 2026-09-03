# tests/test_partner_upgrades.py
"""
Unit tests for Soldier Boy partner upgrade suite and self-upgrade engine.
Tests Calendar, Inbox, Maps, Cloud Docs, Smart Home, Self-Upgrade, and System Skills integration.
"""

import pytest
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.calendar_intel import CalendarIntelManager
from modules.inbox_intel import InboxIntelManager
from modules.maps_nav import MapsNavigationEngine
from modules.cloud_docs import CloudDocumentManager
from modules.smart_home import SmartHomeManager
from modules.self_upgrade import SoldierBoySelfUpgrade
from core.system_skills import SystemSkillEngine
from core.wake_word import WakeWordEngine


def test_calendar_intel():
    cal = CalendarIntelManager()
    events = cal.get_upcoming_events()
    assert isinstance(events, list)
    reminders = cal.format_soldierboy_reminders()
    assert isinstance(reminders, str)
    assert len(reminders) > 0


def test_inbox_intel():
    inbox = InboxIntelManager()
    urgent = inbox.scan_urgent()
    assert isinstance(urgent, list)
    tldr = inbox.get_tldr_summary()
    assert isinstance(tldr, str)
    assert "urgent" in tldr.lower() or "inbox" in tldr.lower() or "clear" in tldr.lower()


def test_maps_nav():
    nav = MapsNavigationEngine()
    loc = nav.get_current_location()
    assert "city" in loc or "lat" in loc
    tacos = nav.search_nearby_poi("tacos")
    assert len(tacos) > 0
    route = nav.get_route_directions("HQ")
    assert "soldierboy_prompts" in route
    food_resp = nav.format_nearby_food_response("tacos")
    assert "taco" in food_resp.lower()


def test_cloud_docs():
    docs = CloudDocumentManager()
    results = docs.search_documents("Final_Final")
    assert len(results) > 0
    summary = docs.get_document_summary("Final_Final")
    assert "Final_Final" in summary or "Google" in summary or "Dropbox" in summary


def test_smart_home():
    sh = SmartHomeManager()
    res_arrival = sh.handle_arrival()
    assert "beautiful bastard" in res_arrival.lower() or "72" in res_arrival
    res_lights = sh.set_light_state(True, 80)
    assert "ON" in res_lights
    res_lock = sh.set_lock_state(True)
    assert "locked" in res_lock.lower()


def test_self_upgrade():
    upgrader = SoldierBoySelfUpgrade()
    audit = upgrader.inspect_code_and_logs()
    assert audit["status"] == "Audit Complete"
    assert audit["inspected_files"] > 0
    fb = upgrader.record_skill_feedback("test_skill", True)
    assert "hit the mark" in fb
    snap = upgrader.create_skill_snapshot("navigation_boost")
    assert "Created versioned backup" in snap
    rollback = upgrader.rollback_skill("navigation_boost")
    assert "Successfully rolled back" in rollback or "No backup" in rollback
    whisper = upgrader.format_level_up_whisper()
    assert "partner" in whisper.lower()


def test_system_skill_engine():
    engine = SystemSkillEngine()

    # 1. Calendar
    res = engine.try_execute("what is on my calendar today?")
    handled, msg = res[0], res[1]
    payload = res[4]
    assert handled and ("meeting" in msg.lower() or "calendar" in msg.lower() or "briefing" in msg.lower() or "double-booked" in msg.lower() or "clear" in msg.lower())
    assert payload["action_type"] == "CALENDAR"
    assert len(payload["findings"]) > 0

    # 2. Inbox
    res = engine.try_execute("scan my inbox for urgent email")
    handled, msg = res[0], res[1]
    payload = res[4]
    assert handled and len(msg) > 0
    assert payload["action_type"] == "INBOX"

    # 3. Maps / Food
    res = engine.try_execute("find the nearest 24hr taco spot for my hangry ass")
    handled, msg = res[0], res[1]
    payload = res[4]
    assert handled and "taco" in msg.lower()
    assert payload["action_type"] == "MAPS"

    # 4. Cloud Docs
    res = engine.try_execute("find document Final_Final_REALLYFINAL_v3.pdf")
    handled, msg = res[0], res[1]
    payload = res[4]
    assert handled and ("Final_Final" in msg or "report" in msg.lower())
    assert payload["action_type"] == "FILE SEARCH"

    # 5. Smart Home Arrival
    res = engine.try_execute("I'm home, you beautiful bastard")
    handled, msg = res[0], res[1]
    payload = res[4]
    assert handled and ("beautiful bastard" in msg.lower() or "72" in msg)
    assert payload["action_type"] == "SMART HOME"

    # 6. Self Upgrade Audit & Codebase Inspection
    res = engine.try_execute("audit code and check for mistakes")
    handled, msg = res[0], res[1]
    payload = res[4]
    assert handled and ("Audit Complete" in msg or "files audited" in msg)
    assert payload["action_type"] == "SYSTEM AUDIT"

    res_upg = engine.try_execute("see what are upgarded in your codebase and see what are good and what are new to you")
    handled_upg, msg_upg = res_upg[0], res_upg[1]
    assert handled_upg and "files audited" in msg_upg

    # 7. Flexible Google Search
    res_srch = engine.try_execute("do some Google Search on latest news")
    handled_srch, msg_srch, is_srch, q_srch, payload_srch = res_srch
    assert handled_srch and is_srch and q_srch == "latest news" and len(msg_srch) > 0
    assert payload_srch["action_type"] == "SEARCH"
    assert "findings" in payload_srch

    # 8. Sarcastic Printer Trigger
    res = engine.try_execute("Oh great, printer jammed again")
    handled, msg = res[0], res[1]
    assert handled and "printer" in msg.lower()


def test_structured_hud_engine():
    from core.structured_hud_engine import StructuredHUDEngine
    hud = StructuredHUDEngine()
    
    # Payload building & priority sorting
    raw = [
        {"title": "Low Priority Item", "snippet": "Normal news update", "url": "https://example.com/1"},
        {"title": "URGENT BREAKING NEWS", "snippet": "Critical alert update", "url": "https://example.com/2", "is_breaking": True}
    ]
    payload = hud.build_structured_payload("Test Topic", "SEARCH", raw, "Spoken summary text")
    assert payload["topic"] == "Test Topic"
    assert payload["has_breaking_news"] is True
    # Priority sorting should place breaking news first
    assert payload["findings"][0]["is_breaking"] is True

    # Cache functionality
    cached = hud.cache.get("Test Topic")
    assert cached is not None
    assert cached["topic"] == "Test Topic"


def test_wake_word_aliases():
    wake = WakeWordEngine()
    matched, phrase = wake.check_stt_text_for_wake_or_aliases("hey soldier where are you")
    assert matched and phrase == "Hey Soldier"
    matched_joke, _ = wake.check_stt_text_for_wake_or_aliases("joke what is on the schedule")
    assert matched_joke
    assert wake.silence_timeout_sec == 2.5


def test_hud_panel():
    from frontend.hud_panel import HUDPanelManager
    hud = HUDPanelManager()
    data = hud.show_action_hud(
        title="Test HUD Search",
        action_type="SEARCH",
        details="Found 3 results for query",
        preview_link_or_file="https://google.com"
    )
    assert data["status"] == "LIVE HUD ACTIVE"
    assert "Here, see the screen, partner" in data["spoken_intro"]

