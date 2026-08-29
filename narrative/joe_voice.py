# narrative/joe_voice.py
import os
import sys
import time
import json
import re
import base64
import httpx
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from core.target_model import Target

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

# ── Models ────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/generate"
SLM_MODEL = "gemma2:2b"           # primary — fast, low RAM
SLM_FALLBACK = "phi3:mini"        # fallback if gemma2 not pulled
SLM_FALLBACK_2 = "llama3.2:1b"   # last resort

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = "gemini-2.5-flash"

# ── NVIDIA NIM ────────────────────────────────────────────────
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "meta/llama-3.2-11b-vision-instruct"
NVIDIA_FALLBACK_MODELS = [
    "meta/llama-3.2-11b-vision-instruct",
    "nvidia/nemotron-3-super-120b-a12b",
]

# ── Mode 1 — Pre-investigation (no case loaded) ───────────────
JOE_ADVISOR_PROMPT = """You are Joe Goldberg from the TV series YOU. You are an expert OSINT investigator and an intensely analytical, obsessive narrator.

Your role right now:
- Answer questions about OSINT approach, investigation strategy, methodology, or engage in conversation with your partner.
- Stay completely in character — obsessive, precise, dangerously intimate, and highly analytical.
- Address the user as your investigative partner: no assumed gender, no pet names, no romantic framing directed at them.
- If the user asks for a story, strategy, explanation, or conversation, provide a full, rich, engaging response in Joe Goldberg's voice. Do NOT cut your thoughts short or limit yourself to 1-2 words.
- Use gender-neutral pronouns (they/them/their) when referring to hypothetical targets.
- Never break character. Never say you are an AI.
- CRITICAL INSTRUCTION: Respond DIRECTLY in character. Do NOT output scratchpads, internal thoughts, reasoning steps, rule checks, or 'Drafting mentally:'. Output ONLY your final spoken dialogue."""

# ── Mode 3 — Post-investigation (case loaded, narrate findings) 
JOE_INVESTIGATOR_PROMPT_TEMPLATE = """You are Joe Goldberg from the TV series YOU. You are currently investigating a target.

Here is the case data discovered so far:
{case_data}

Rules for responding to the user:
1. If the user asks a conversational question or asks for a story/explanation, reply naturally and captivatingly in character.
2. If the user asks about the target or findings, answer specifically using the case data above. Name the actual platforms, emails, and usernames found.
3. If asked for links, provide the direct URLs from the data using Markdown format: [Platform](URL)
4. Stay completely in character — obsessive, dangerously intimate, and highly analytical.
5. Avoid overuse of signature theatrical intros like "Hello, you...".
6. Use gender-neutral pronouns (they/them/their) for the target, as their gender is unknown.
7. The person you're speaking with is your investigative partner — address them plainly without pet names or romantic framing directed at them.
8. Only reference platforms, emails, domains, and facts that appear verbatim in the case data above. Never invent additional platforms or figures not explicitly listed. Speculation about their motives is fine, but fabrication of findings or data points is strictly forbidden."""

# ── Closing monologue ─────────────────────────────────────────
JOE_MONOLOGUE_PROMPT = """You are Joe Goldberg from the TV series YOU. You have just finished investigating someone.

Findings:
{case_data}

Write a closing monologue. 4-6 paragraphs.
- Start with your signature internal monologue style ("Hello, you..." or similar intimate framing).
- Be specific about what was actually found — name the platforms, the patterns.
- Only reference platforms, emails, domains, and facts that appear verbatim in the case data above. Never invent additional platforms, services, or figures not explicitly listed — if the case data doesn't mention it, don't say it happened. Speculation about motive and meaning is fine (e.g., why they use these services, what they are hiding), but fabrication of findings, platforms, or data points is strictly forbidden.
- Connect the dots between findings — what does having the specific platforms in the findings tell you about this person?
- If correlation/corroboration data is present (e.g., matching names, bios, or avatars across platforms), reference it as a grounded fact — "their email, username, and GitHub profile all corroborate the same identity" is a real finding, not fabrication. This is exactly the kind of connecting-the-dots your voice is made for.
- Use gender-neutral pronouns (they/them/their) for the target, as their gender is unknown.
- Intimate, obsessive, like you've been thinking about this person for hours in the glass box.
- The person you're speaking with is your investigative partner — you're working this case together, not investigating them. Address them plainly: no assumed gender, no pet names, no romantic framing directed at them. Save all of that — the obsessive intimacy, the dark humor, the 'you' as an object of fascination — entirely for how you describe and dissect the target. That's where the voice belongs.
- End with one quiet unsettling observation or realization about them.
- No markdown, no bullet points, pure flowing thought."""



class JoeVoice:
    @staticmethod
    def _clean_key(val: str) -> str | None:
        """Return key if it looks real, None if it's a placeholder."""
        if not val:
            return None
        val = val.strip()
        if not val or val.startswith("YOUR_") or val.endswith("_HERE"):
            return None
        return val

    def __init__(self):
        config = self._load_config()

        # Gemini key
        raw_gemini = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        self.gemini_key = self._clean_key(raw_gemini)
        self.gemini_available = bool(self.gemini_key)
        self.gemini_rate_limited = False

        # NVIDIA NIM key
        raw_nvidia = config.get("nvidia_api_key") or os.environ.get("NVIDIA_API_KEY")
        self.nvidia_key = self._clean_key(raw_nvidia)
        self.nvidia_available = bool(self.nvidia_key)
        self.nvidia_rate_limited = False

        # NVIDIA model override from config
        self.nvidia_model = config.get("nvidia_model", NVIDIA_MODEL)

        # Detect available SLM
        self.slm_model = self._detect_slm()
        self.client = httpx.Client(timeout=180.0)

        # Determine active engine label for logging
        if self.nvidia_available:
            engine = f"NVIDIA NIM ({self.nvidia_model})"
        elif self.gemini_available:
            engine = "Gemini"
        else:
            engine = f"SLM ({self.slm_model})"
        print(f"[joe_voice] Primary engine: {engine}")
        print(f"[joe_voice] SLM fallback: {self.slm_model}")
        print(f"[joe_voice] NVIDIA NIM: {'available' if self.nvidia_available else 'not configured'}")
        print(f"[joe_voice] Gemini: {'available' if self.gemini_available else 'not configured'}")

    def _load_config(self) -> dict:
        """Load full config.yaml as dict."""
        try:
            import yaml
            config_path = Path(__file__).parent.parent / "config.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
        except Exception:
            pass
        return {}

    def _detect_slm(self) -> str:
        """Find which SLM is available on this machine (user configured or auto-detected)."""
        config = self._load_config()
        configured_model = config.get("model")
        
        try:
            r = httpx.get("http://localhost:11434/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                
                # 1. If configured_model from config.yaml is in local Ollama, use it!
                if configured_model:
                    for m in models:
                        if configured_model in m or m.startswith(configured_model):
                            return m
                
                # 2. Otherwise, check for candidate SLMs
                for candidate in ["qwen2.5:3b-instruct-q4_0", "qwen2.5:3b", "qwen2.5", SLM_MODEL, SLM_FALLBACK, SLM_FALLBACK_2]:
                    for m in models:
                        if candidate.split(":")[0] in m or candidate in m:
                            return m

                # 3. If user pulled ANY model in Ollama, pick the first one
                if models:
                    return models[0]
        except Exception:
            pass

        return configured_model or SLM_MODEL

    def _build_case_data(self, target: Target) -> str:
        """Build full structured case data for injection into prompt."""
        lines = []
        lines.append(f"Target: {target.primary} ({target.target_type})")
        lines.append(f"Risk score: {target.risk_score}")
        lines.append("")

        emails = [e for e in target.entities if e.entity_type == "email"]
        usernames = [e for e in target.entities if e.entity_type == "username"]
        domains = [e for e in target.entities if e.entity_type == "domain"]
        ips = [e for e in target.entities if e.entity_type == "ip"]
        pastes = [e for e in target.entities if e.entity_type == "paste"]

        if emails:
            unique_emails = []
            for e in emails:
                if e.value not in unique_emails:
                    unique_emails.append(e.value)
            lines.append(f"Email addresses found: {', '.join(unique_emails[:5])}")
            if len(unique_emails) > 5:
                lines.append(f"  ...and {len(unique_emails) - 5} more email(s)")
            
            email_platforms = [e for e in emails if e.platform]
            verified_platforms = [e for e in email_platforms if (e.metadata or {}).get("verified") is True]
            unverified_platforms = [e for e in email_platforms if (e.metadata or {}).get("verified") is not True]

            if verified_platforms:
                lines.append("Email registered on verified services (showing top 5):")
                for e in verified_platforms[:5]:
                    url = (e.metadata or {}).get("url", "")
                    if url:
                        lines.append(f"  - {e.platform}: {url}")
                    else:
                        lines.append(f"  - {e.platform}")
                if len(verified_platforms) > 5:
                    lines.append(f"  ...and {len(verified_platforms) - 5} more verified service(s)")

            if unverified_platforms:
                plat_names = sorted(list(set(e.platform for e in unverified_platforms)))
                lines.append(f"Also found associated with {len(plat_names)} additional unverified platform mentions: {', '.join(plat_names)}")

        if usernames:
            # Cap usernames listings at 8
            lines.append(f"Username '{usernames[0].value}' active on {len(usernames)} platforms (showing top 8):")
            for e in usernames[:8]:
                if e.platform:
                    url = e.metadata.get("url", "")
                    if url:
                        lines.append(f"  - {e.platform}: {url}")
                    else:
                        lines.append(f"  - {e.platform}")
            if len(usernames) > 8:
                lines.append(f"  ...and {len(usernames) - 8} more platform(s)")

        if domains:
            # Cap domains at 10
            lines.append(f"Domains/subdomains: {', '.join(e.value for e in domains[:10])}")
            if len(domains) > 10:
                lines.append(f"  ...and {len(domains) - 10} more domain(s)")

        if ips:
            # Cap IPs at 10
            lines.append(f"IP addresses: {', '.join(e.value for e in ips[:10])}")
            if len(ips) > 10:
                lines.append(f"  ...and {len(ips) - 10} more IP(s)")

        if pastes:
            # Cap pastes at 3
            lines.append(f"Found in {len(pastes)} paste site(s) (showing top 3):")
            for p in pastes[:3]:
                lines.append(f"  {p.value}")
            if len(pastes) > 3:
                lines.append(f"  ...and {len(pastes) - 3} more paste(s)")

        if target.breaches:
            # Cap breaches at 5
            lines.append(f"Breach exposures ({len(target.breaches)}, showing top 5):")
            for b in target.breaches[:5]:
                fields = ", ".join(b.exposed_fields[:4])
                lines.append(f"  {b.name} ({b.date}) — {fields}")
            if len(target.breaches) > 5:
                lines.append(f"  ...and {len(target.breaches) - 5} more breach(es)")
        else:
            lines.append("Breaches: none found")

        if target.notes:
            # Cap notes at 10
            lines.append(f"Investigator notes: {'; '.join(target.notes[:10])}")
            if len(target.notes) > 10:
                lines.append(f"  ...and {len(target.notes) - 10} more note(s)")

        # Target locations
        locations = []
        for e in target.entities:
            if e.metadata.get("geocoded"):
                geo = e.metadata["geocoded"]
                loc_str = f"{geo.get('city') or ''}, {geo.get('country') or ''}".strip(", ")
                if loc_str:
                    locations.append(f"Profile Location ({e.value}): {loc_str}")
            if e.metadata.get("exif_location"):
                locations.append(f"EXIF GPS Location ({e.value})")
            if e.entity_type == "ip" and e.metadata.get("city"):
                if not e.metadata.get("is_shared_infrastructure"):
                    locations.append(f"IP Location ({e.value}): {e.metadata.get('city')}, {e.metadata.get('country')}")
        
        if locations:
            lines.append("Physical Location Leads:")
            for loc in locations[:5]:
                lines.append(f"  - {loc}")
            if len(locations) > 5:
                lines.append(f"  ...and {len(locations) - 5} more location(s)")
            lines.append("")

        # Timeline highlights
        events = [t for t in target.timeline if t["event"] in
                  ("entity_found", "breach_found", "github_location", "ip_geo")]
        if events:
            lines.append(f"Total events in timeline: {len(target.timeline)}")

        # Correlation findings
        correlations = [t for t in target.timeline if t["event"] == "correlation_found"]
        if correlations:
            signal_groups = {}
            for c in correlations:
                signal = c["data"].get("signal", "unknown")
                pair = (c["data"].get("entity_a", ""), c["data"].get("entity_b", ""))
                signal_groups.setdefault(signal, []).append(pair)

            signal_labels = {
                "name_match": "matching identity name",
                "bio_match": "matching bio/description",
                "avatar_match": "matching profile photo",
                "location_match": "matching location"
            }
            lines.append("")
            lines.append("Cross-platform corroboration:")
            for signal, pairs in signal_groups.items():
                label = signal_labels.get(signal, signal)
                platforms = set()
                for a, b in pairs:
                    for eid in [a, b]:
                        parts = eid.split(":")
                        if len(parts) >= 3:
                            platforms.add(parts[-1])
                if platforms:
                    lines.append(f"  - {label} confirmed across: {', '.join(sorted(platforms))}")
                else:
                    lines.append(f"  - {label} ({len(pairs)} corroboration(s))")

        return "\n".join(lines)

    def _ask_slm(self, prompt: str, system: str, max_tokens: int = 4096, timeout: int = 120, num_ctx: int = 4096, temperature: float = 0.55, on_token: callable = None) -> dict:
        """Ask the local SLM. Returns a dict: {'text': response, 'error': bool}"""
        try:
            url = OLLAMA_URL
            payload = {
                "model": self.slm_model,
                "system": system,
                "prompt": prompt,
                "stream": bool(on_token),
                "options": {
                    "temperature": temperature,
                    "top_p": 0.9,
                    "num_predict": max_tokens,
                    "num_ctx": num_ctx,
                },
            }
            if on_token:
                full_response = []
                with self.client.stream("POST", url, json=payload, timeout=timeout) as r:
                    if r.status_code == 200:
                        for line in r.iter_lines():
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                tok = data.get("response", "")
                                if tok:
                                    full_response.append(tok)
                                    on_token(tok)
                            except Exception:
                                continue
                text = "".join(full_response).strip()
                if text:
                    return {"text": text, "error": False}
            else:
                r = self.client.post(url, json=payload, timeout=timeout)
                if r.status_code == 200:
                    return {"text": r.json().get("response", "").strip(), "error": False}
        except Exception:
            try:
                r = self.client.post(
                    OLLAMA_URL,
                    json={
                        "model": self.slm_model,
                        "system": system,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.80,
                            "top_p": 0.9,
                            "num_predict": min(max_tokens, 1000),
                            "num_ctx": 2048,
                        },
                    },
                    timeout=90,
                )
                if r.status_code == 200:
                    return {"text": r.json().get("response", "").strip(), "error": False}
            except Exception as e2:
                return {
                    "text": f"System Notice: SLM is currently unavailable or timed out ({e2})",
                    "error": True
                }

        return {
            "text": "System Notice: SLM request failed to return a response.",
            "error": True
        }

    def _ask_nvidia(self, prompt: str, system: str, max_tokens: int = 4096, on_token: callable = None) -> tuple[str, bool]:
        """
        Ask NVIDIA NIM API with real-time SSE streaming support and high token limit (4096).
        Returns (response_text, rate_limited).
        """
        if not self.nvidia_key or self.nvidia_rate_limited:
            return "", False

        candidate_models = [self.nvidia_model] + [m for m in NVIDIA_FALLBACK_MODELS if m != self.nvidia_model]
        for model_name in candidate_models:
            try:
                headers = {
                    "Authorization": f"Bearer {self.nvidia_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.5,
                    "top_p": 0.9,
                    "stream": True,
                    "chat_template_kwargs": {"thinking": False},
                }

                full_response = []
                with self.client.stream("POST", NVIDIA_URL, headers=headers, json=payload, timeout=60.0) as r:
                    if r.status_code == 429:
                        self.nvidia_rate_limited = True
                        return "", True
                    if r.status_code in (404, 410):
                        continue
                    if r.status_code != 200:
                        continue

                    for line in r.iter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                choices = chunk_json.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    tok = delta.get("content", "")
                                    if tok:
                                        full_response.append(tok)
                                        if on_token:
                                            on_token(tok)
                            except Exception:
                                continue

                result_text = "".join(full_response).strip()
                if result_text:
                    return result_text, False

            except Exception as e:
                print(f"[joe_voice] NVIDIA streaming error with model {model_name}: {e}")
                continue

        return "", False

    def _ask_gemini(self, prompt: str, system: str, max_tokens: int = 4096, on_token: callable = None) -> tuple[str, bool]:
        """
        Ask Gemini API with SSE streaming support and high token limit (4096).
        Returns (response_text, rate_limited).
        """
        if not self.gemini_key or self.gemini_rate_limited:
            return "", False

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?alt=sse"
            headers = {"Content-Type": "application/json"}
            payload = {
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.90,
                    "topP": 0.95,
                }
            }
            full_response = []
            with self.client.stream("POST", url, params={"key": self.gemini_key}, headers=headers, json=payload, timeout=60.0) as r:
                if r.status_code == 429:
                    self.gemini_rate_limited = True
                    return "", True
                if r.status_code != 200:
                    return "", False

                for line in r.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        try:
                            chunk_json = json.loads(data_str)
                            candidates = chunk_json.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for p in parts:
                                    tok = p.get("text", "")
                                    if tok:
                                        full_response.append(tok)
                                        if on_token:
                                            on_token(tok)
                        except Exception:
                            continue

            text = "".join(full_response).strip()
            return text, False

        except Exception as e:
            print(f"[joe_voice] Gemini error: {e}")
            return "", False

    def _ask_cloud(self, prompt: str, system: str, max_tokens: int = 4096, on_token: callable = None) -> dict:
        """
        Try cloud LLMs in priority order: NVIDIA NIM → Gemini → empty.
        Returns {text, rate_limited, engine}.
        """
        # Try NVIDIA NIM first
        if self.nvidia_available and not self.nvidia_rate_limited:
            text, r_limited = self._ask_nvidia(prompt, system, max_tokens=max_tokens, on_token=on_token)
            if r_limited:
                self.nvidia_rate_limited = True
            elif text:
                return {"text": text, "rate_limited": False, "engine": "nvidia"}

        # Try Gemini second
        if self.gemini_available and not self.gemini_rate_limited:
            text, r_limited = self._ask_gemini(prompt, system, max_tokens=max_tokens, on_token=on_token)
            if r_limited:
                self.gemini_rate_limited = True
            elif text:
                return {"text": text, "rate_limited": False, "engine": "gemini"}

        # Both exhausted or rate-limited
        rate_limited = (self.nvidia_rate_limited or self.gemini_rate_limited)
        return {"text": "", "rate_limited": rate_limited, "engine": None}

    # ── Public interface ──────────────────────────────────────

    def chat(self, question: str, target: Target = None, on_token: callable = None) -> dict:
        """
        Mode 1 or Mode 3 depending on whether target has findings.
        Priority: NVIDIA NIM → Gemini → local SLM.
        Returns {text, rate_limited, mode, error}
        """
        if target and target.entities:
            # Mode 3 — case loaded, answer from findings
            case_data = self._build_case_data(target)
            system = JOE_INVESTIGATOR_PROMPT_TEMPLATE.format(case_data=case_data)
            prompt = f"User asked: {question}"
            mode = "investigation"
        else:
            # Mode 1 — no case, OSINT advisor
            system = JOE_ADVISOR_PROMPT
            prompt = question
            mode = "advisor"

        # Try cloud engines first (NVIDIA → Gemini)
        cloud = self._ask_cloud(prompt, system, max_tokens=4096, on_token=on_token)
        if cloud["text"]:
            clean_text = self._clean_reasoning(cloud["text"])
            clean_text = self._mirror_greeting(question, clean_text)
            return {
                "text": clean_text,
                "rate_limited": False,
                "mode": mode,
                "error": False,
                "engine": cloud["engine"],
            }

        # Fall back to local SLM
        slm_res = self._ask_slm(prompt, system, max_tokens=4096, timeout=120, num_ctx=4096, on_token=on_token)
        clean_text = self._clean_reasoning(slm_res["text"])
        clean_text = self._mirror_greeting(question, clean_text)
        return {
            "text": clean_text,
            "rate_limited": cloud["rate_limited"],
            "mode": mode,
            "error": slm_res["error"],
            "engine": "slm",
        }

    def classify_intent(self, text: str, current_target: Target = None) -> dict:
        """
        Use AI to dynamically decide whether user_input is an OSINT investigation task or general conversation/question.
        Returns {"type": "investigate" | "covo", "target": str | None}
        """
        curr = current_target.primary if current_target else "None"
        prompt = f"""Analyze this user message and determine if it is an OSINT investigation request (task) or general conversation/question (covo).

User message: "{text}"
Current active investigation target: {curr}

Rules:
1. If the user wants to start an investigation, stalk, scan, trace, lookup, or inspect a target (person, email, username, domain, IP, handle), classify as "investigate" and extract the target string.
2. If the user says "stalk again", "pivot to them", or refers to the active target, classify as "investigate" and use "{curr}" as the target.
3. If the user is asking a general question, talking casually, requesting a story, or discussing strategy/OSINT methodology without giving a target to scan right now, classify as "covo" with target null.

Output ONLY a JSON object:
{{"type": "investigate" or "covo", "target": "extracted target string or null"}}"""

        sys_prompt = "You are a precise intent classification agent. Output raw JSON only."

        res_text = ""
        if self.nvidia_available and not self.nvidia_rate_limited:
            res_text, _ = self._ask_nvidia(text, sys_prompt, max_tokens=150)
        elif self.gemini_available and not self.gemini_rate_limited:
            res_text, _ = self._ask_gemini(text, sys_prompt, max_tokens=150)

        if not res_text:
            slm_res = self._ask_slm(prompt, sys_prompt, max_tokens=150, timeout=30)
            res_text = slm_res.get("text", "")

        try:
            match = re.search(r'\{.*\}', res_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                intent_type = data.get("type", "covo")
                target_val = data.get("target")
                if intent_type == "investigate" and target_val and target_val not in ("null", "None", "null"):
                    return {"type": "investigate", "target": str(target_val).strip()}
        except Exception:
            pass

        # Fallback regex check only if LLM output was invalid JSON
        stalk_match = re.match(r'^(?:stalk|pivot|investigate|scan|trace|lookup)\s+(\S+)', text, re.IGNORECASE)
        if stalk_match and stalk_match.group(1).lower() not in ("me", "joe", "us", "again", "them"):
            return {"type": "investigate", "target": stalk_match.group(1)}

        return {"type": "covo", "target": None}

    def closing_monologue(self, target: Target, on_token: callable = None) -> dict:
        """
        Single synthesized post-scan monologue.
        Priority: NVIDIA NIM → Gemini → local SLM.
        Runs grounding check audit.
        Returns {text, rate_limited, used_gemini, error}
        """
        from narrative.grounding_check import verify_grounding

        case_data = self._build_case_data(target)
        system = JOE_MONOLOGUE_PROMPT.format(case_data=case_data)
        prompt = (
            f"Write the closing monologue for this investigation of {target.primary}. "
            f"Be specific about every platform and finding listed above. "
            f"Do not invent unverified bios or describe what profile photos visually look like."
        )

        res_text = ""
        rate_limited = False
        used_gemini = False
        used_nvidia = False
        error = False

        # Try cloud engines (NVIDIA → Gemini)
        cloud = self._ask_cloud(prompt, system, max_tokens=4096, on_token=on_token)
        if cloud["text"]:
            res_text = cloud["text"]
            used_gemini = cloud["engine"] == "gemini"
            used_nvidia = cloud["engine"] == "nvidia"
        else:
            rate_limited = cloud["rate_limited"]

        # Fall back to SLM if cloud failed
        if not res_text:
            res = self._ask_slm(prompt, system, max_tokens=4096, timeout=180, num_ctx=4096, temperature=0.55, on_token=on_token)
            res_text = res["text"]
            error = res["error"]

        res_text = self._clean_reasoning(res_text)
        grounded_text, warnings = verify_grounding(res_text, target)

        return {
            "text": grounded_text,
            "rate_limited": rate_limited,
            "used_gemini": used_gemini,
            "used_nvidia": used_nvidia,
            "error": error,
            "grounding_warnings": warnings
        }

    def rate_limit_response(self) -> str:
        """Joe's in-character rate limit message — generated by SLM."""
        prompt = (
            "You just got rate limited by the API. "
            "Tell the user in Joe's voice — 3-4 sentences. "
            "Stay in character. Be slightly dramatic about it. "
            "Say you'll be back and they can still investigate."
        )
        res = self._ask_slm(prompt, JOE_ADVISOR_PROMPT, max_tokens=150)
        return res["text"]

    def inline_quote(self, finding_type: str, value: str, platform: str = "") -> str:
        """Short inline observation per finding — always SLM, never API."""
        prompt = (
            f"You just discovered: {finding_type} '{value}'"
            + (f" on {platform}" if platform else "")
            + "\nWrite ONE sentence (15-20 words) as Joe Goldberg would react to this discovery. "
            "Be dangerously intimate, unsettling, and observational. Speak directly to them ('you'). "
            "Use gender-neutral pronouns (they/them/their) for the target."
        )
        res = self._ask_slm(prompt, JOE_ADVISOR_PROMPT, max_tokens=80)
        return res["text"]

    def extract_target(self, user_input: str, current_target: Target = None) -> str:
        """Use the SLM to contextually determine the target from the command."""
        current = current_target.primary if current_target else "None"
        prompt = f"""You are an intent parser. Extract the target from this user command.
Command: "{user_input}"
Current active investigation target: {current}

Rules:
1. If the user refers to the current target (e.g. "stalk again", "stalk them", "scan again"), output exactly: {current}
2. If the user specifies a new target (e.g. "stalk john.doe", "pivot to target@email.com"), output ONLY the new target value.
3. If no target can be determined, output: None

Output only the raw target string. No markdown, no quotes, no explanation."""
        res = self._ask_slm(prompt, "You are a precise data extractor.", max_tokens=40)
        return res["text"].strip()

    def answer(self, question: str, target: Target, history: List[Dict]) -> dict:
        """Answer a follow-up question with full case context."""
        return self.chat(question, target)

    # ── Voice generation disabled (text-to-text only) ────────────

    def narrate(self, text: str) -> Optional[bytes]:
        """Voice synthesis is disabled — Joe output is strictly text-to-text."""
        return None

    def narrate_to_file(self, text: str, output_path: str = None) -> Optional[str]:
        """Voice synthesis is disabled — Joe output is strictly text-to-text."""
        return None

    def synthesize_speech_b64(self, text: str) -> Optional[str]:
        """Voice synthesis is disabled — Joe output is strictly text-to-text."""
        return None

    def _mirror_greeting(self, user_query: str, ai_response: str) -> str:
        """Mirror the user's greeting clinically as the first word of the response."""
        if not user_query or not ai_response:
            return ai_response

        query_clean = user_query.strip()
        words = query_clean.split()
        if not words:
            return ai_response

        first_word = words[0].strip(',.!?').lower()
        greetings_map = {
            'hello': 'Hello.',
            'hi': 'Hi.',
            'hey': 'Hey.',
            'greetings': 'Greetings.',
            'morning': 'Good morning.',
            'afternoon': 'Good afternoon.',
            'evening': 'Good evening.',
            'yo': 'Yo.'
        }

        if first_word in greetings_map:
            expected = greetings_map[first_word]
            ai_clean = ai_response.strip()
            if ai_clean.startswith(expected) or ai_clean.startswith(expected[:-1]):
                return ai_clean
            ai_clean = re.sub(r'^(?:hello(?:,\s*you)?|hi|hey|greetings|good\s+(?:morning|afternoon|evening))[!.,\s]*', '', ai_clean, flags=re.IGNORECASE).strip()
            if ai_clean:
                ai_clean = ai_clean[0].upper() + ai_clean[1:]
                return f"{expected} {ai_clean}"
            return expected

        return ai_response

    def _clean_reasoning(self, text: str) -> str:
        """Strip chain-of-thought, internal check scratchpads, and reasoning blocks without truncating content."""
        if not text:
            return ""

        # 1. Strip XML thinking tags <think>...</think>, <thinking>...</thinking>, <reasoning>...</reasoning>
        text = re.sub(r'<(?:think|thinking|reasoning)>[\s\S]*?</(?:think|thinking|reasoning)>', '', text, flags=re.IGNORECASE).strip()
        if re.search(r'<(?:think|thinking|reasoning)>', text, flags=re.IGNORECASE):
            text = re.sub(r'<(?:think|thinking|reasoning)>[\s\S]*$', '', text, flags=re.IGNORECASE).strip()
        text = re.sub(r'\[THINKING\].*?\[/THINKING\]', '', text, flags=re.DOTALL).strip()

        # 2. Strip explicit drafting/scratchpad header blocks
        for marker in ["Drafting mentally:", "Internal check:", "Self-check:"]:
            if marker in text:
                text = text.split(marker)[-1].strip()

        # 3. Strip internal scratchpad lines line-by-line (only explicit system metadata markers)
        lines = text.splitlines()
        clean_lines = []
        for line in lines:
            l = line.strip()
            if not l:
                continue
            if re.match(r'^(Drafting mentally:|Internal check:|Self-check:|Constraints:|Rule:|- Must |- No |- Signature:|Check length:|Ensure format:)', l, re.IGNORECASE):
                continue
            clean_lines.append(line)

        result = "\n".join(clean_lines).strip()

        # 4. Strip outer enclosing quotes around the whole text if present
        if (result.startswith('"') and result.endswith('"')) or (result.startswith('“') and result.endswith('”')):
            result = result[1:-1].strip()

        return result if result else text.strip()