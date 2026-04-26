<div align="center">
  <img src="assets/joe.png" alt="Joe Goldberg" width="600"/>

  # Joe Goldberg

  **Autonomous OSINT Investigator — fully local, zero cost**

  ![Python](https://img.shields.io/badge/Python-3.10%2B-c0392b?style=flat-square&logo=python&logoColor=white)
  ![LLM](https://img.shields.io/badge/LLM-Gemini%20%7C%20Ollama-e8a020?style=flat-square)
  ![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS-8b2010?style=flat-square)
  ![License](https://img.shields.io/badge/License-GPL--3.0-blue?style=flat-square)
  ![Status](https://img.shields.io/badge/Status-Active%20Development-2d7a3a?style=flat-square)

  > *"I notice everything."*
</div>

---

## What is Joe Goldberg?

Joe Goldberg is an OSINT investigation tool named after the obsessive, detail-oriented character from the series YOU. Just like Joe, this tool notices everything — it gathers publicly available information about a target, connects the dots, and narrates findings in his voice.

Built for penetration testers, bug bounty hunters, CTF players, and security researchers. No API keys for recon. No subscriptions. No data leaving your machine.

---

## What it does

Give Joe a target — an email, username, domain, IP, or full name — and he investigates it. He scans hundreds of platforms for linked accounts, checks breach databases, pulls DNS and certificate records, harvests linked emails, and builds a complete picture of the target's digital footprint.

While scanning, Joe speaks. Every significant find gets a brief observation in his voice. When the investigation is complete, he delivers a full closing monologue — connecting every dot, reading between the lines, the way only Joe would.

Everything is saved as a case file. You can resume any investigation later, add notes, ask Joe follow-up questions, and export a full HTML report.

---

## Interface

<div align="center">
  <img src="assets/Interface.png" alt="Joe Goldberg Interface" width="800"/>
  <br/>
  <sub>Joe's cinematic terminal UI — red-on-black, inline narration, live findings</sub>
</div>

---

## Features

- Investigates emails, usernames, domains, IPs, and full names
- Username enumeration across 300+ platforms via Sherlock and Maigret
- Email tracking via Holehe (120+ sites) and Gravatar
- Code, commit, and profile intel via deep GitHub reconnaissance
- Paste site mentions via psbdmp and Google Dorking
- IP Geolocation, Proxy/VPN detection, and AbuseIPDB scraping
- Historical domain snapshots via Wayback Machine
- DNS records, WHOIS, subdomain discovery via certificate transparency logs
- Breach database lookups (BreachDirectory) with exposed field details
- Joe narrates inline as findings arrive — one quiet observation per discovery
- Full closing monologue after every investigation
- Persistent case files — resume any investigation at any time
- Free-form chat — ask Joe anything about the current investigation
- HTML report export with timeline, entity table, and risk score
- Desktop app with red cinematic UI + Joe's image in the background
- Terminal CLI with the same full experience
- Callable as a system command from anywhere — just type `joe`

---

## Requirements

- Python 3.10+
- Git
- Ollama (installed automatically)
- curl (installed by default on Linux/macOS)

---

## Installation
```bash
git clone https://github.com/l4zz3rj0d/JOE-GOLDBERG.git
cd JOE-GOLDBERG

# Linux / macOS
bash install.sh
```

The installer handles Python dependencies, Sherlock, Maigret, Ollama, and pulls the local model automatically.

After installation `joe` works as a system command from any directory — no need to activate a virtualenv or navigate to the project folder.

---

## Narration Configuration

Joe uses **gemma2:2b** running completely locally by default via Ollama for all narration, intent extraction, and context awareness. This ensures your investigation data never leaves your machine.

For faster, richer closing monologues, you can optionally configure a Google Gemini API key.

See the [Gemini Setup Guide](setup.md) for instructions on how to configure your shell and environment for optional Gemini narration.

---

## Usage
```bash
joe                              # desktop app
joe --cli                        # terminal CLI
joe stalk target@email.com       # investigate directly
joe stalk johndoe_87             # username
joe stalk target.com             # domain
joe stalk "john doe"             # full name
```

### Commands

| Command | Description |
|---|---|
| `stalk <target>` | Start a new investigation |
| `resume <target>` | Continue a saved case |
| `pivot <entity>` | Investigate a discovered entity |
| `cases` | List all saved investigations |
| `notes <text>` | Add a note to the current case |
| `export` | Export case as HTML report |
| `help` | Show all commands |
| `exit` | Leave |

Or just type anything — Joe answers questions about the current investigation with full memory of everything found so far.

---

## Desktop Icon (Linux)

After installation, Joe will appear in your system's application menu. Search for **Joe Goldberg** or look under the Security category. You can pin it to your dock or panel just like any other application.

---

## Ethical Use

This tool is for authorized security work only — penetration testing engagements, bug bounty programs, CTF challenges, and authorized investigations.

Do not use against individuals or systems without explicit written authorization. This software is licensed under the **GNU General Public License v3 (GPLv3)**.

---

## Author

**Sree Danush S** (L4ZZ3RJ0D)

Cybersecurity student · Offensive security builder · CyArt intern

[![GitHub](https://img.shields.io/badge/GitHub-l4zz3rj0d-c0392b?style=flat-square&logo=github)](https://github.com/l4zz3rj0d)
[![TryHackMe](https://img.shields.io/badge/TryHackMe-Top%201%25-e8a020?style=flat-square)](https://tryhackme.com/p/l4zz3rj0d)
[![Medium](https://img.shields.io/badge/Medium-@l4zz3rj0d-c8945a?style=flat-square&logo=medium)](https://medium.com/@l4zz3rj0d)

---



<div align="center">
  <sub>Built with obsession. Like Joe would.</sub>
</div>