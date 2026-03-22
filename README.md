<div align="center">
  <img src="assets/joe.jpeg" alt="Joe Goldberg" width="180" style="border-radius: 12px"/>

  # Joe Goldberg

  **Autonomous OSINT Investigator — fully local, zero APIs, zero cost**

  ![Python](https://img.shields.io/badge/Python-3.10%2B-c0392b?style=flat-square&logo=python&logoColor=white)
  ![Ollama](https://img.shields.io/badge/LLM-Ollama%20%2B%20Mistral-e8a020?style=flat-square)
  ![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-8b2010?style=flat-square)
  ![License](https://img.shields.io/badge/License-MIT-c8945a?style=flat-square)
  ![Status](https://img.shields.io/badge/Status-Active%20Development-2d7a3a?style=flat-square)

  > *"I notice everything."*

</div>

---

## What is Joe Goldberg?

Joe Goldberg is a local OSINT investigation tool built for penetration testers, bug bounty hunters, and security researchers. It aggregates publicly available information about a target — emails, usernames, domains, breach history, linked accounts — and narrates findings in the voice of a meticulous, obsessive investigator.

No API keys. No subscriptions. No data leaving your machine. Everything runs locally.

---

## Features

- **Zero API dependency** — uses Sherlock, Maigret, dnspython, python-whois, and crt.sh scraping. Nothing requires registration or payment.
- **Local LLM narration** — Joe speaks using Ollama + Mistral 7B running entirely on your hardware. His voice comments on findings inline as they arrive, then delivers a full closing monologue.
- **Multi-target support** — investigates emails, domains, IPs, usernames, and full names with automatic pipeline routing per target type.
- **Auto-pivot** — when a new entity is discovered mid-investigation (e.g. a secondary email found in a GitHub commit), Joe automatically continues the investigation on it.
- **Persistent case files** — every investigation is saved as structured JSON under `cases/`. Resume any case at any time with full context intact.
- **HTML report export** — export any investigation as a standalone HTML report with a timeline, entity table, breach summary, and risk score.
- **Dual interface** — runs as a desktop app (PyWebView, warm cream + crimson UI) or a clean terminal CLI from anywhere in the system.

---

## Interface
```
     ██╗ ██████╗ ███████╗
     ██║██╔═══██╗██╔════╝
     ██║██║   ██║█████╗
██   ██║██║   ██║██╔══╝
╚█████╔╝╚██████╔╝███████╗
 ╚════╝  ╚═════╝ ╚══════╝

 ██████╗  ██████╗ ██╗     ██████╗ ██████╗ ███████╗██████╗  ██████╗
██╔════╝ ██╔═══██╗██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔════╝
██║  ███╗██║   ██║██║     ██║  ██║██████╔╝█████╗  ██████╔╝██║  ███╗
██║   ██║██║   ██║██║     ██║  ██║██╔══██╗██╔══╝  ██╔══██╗██║   ██║
╚██████╔╝╚██████╔╝███████╗██████╔╝██████╔╝███████╗██║  ██║╚██████╔╝
 ╚═════╝  ╚═════╝ ╚══════╝╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝

  "I notice everything."
  OSINT Investigator — zero APIs, fully local
```

---

## Installation

**Requirements:** Python 3.10+, Git, Ollama
```bash
# Clone the repository
git clone https://github.com/l4zz3rj0d/joe-goldberg.git
cd joe-goldberg

# Linux / macOS — one shot
bash install.sh

# Windows
install.bat
```

The installer handles everything: Python dependencies, Sherlock, Maigret, Ollama, and the Mistral 7B model pull (~4GB, one time only).

After installation, `joe` is registered as a system command available from any directory.

---

## Usage
```bash
# Launch desktop app
joe

# Launch terminal CLI
joe --cli

# Start an investigation directly
joe stalk target@email.com
joe stalk johndoe_87
joe stalk target.com
joe stalk 192.168.1.1
joe stalk "john doe"
```

### CLI Commands

| Command | Description |
|---|---|
| `stalk <target>` | Start a new investigation |
| `resume <target>` | Load and continue a saved case |
| `pivot <entity>` | Investigate a newly discovered entity |
| `cases` | List all saved investigations |
| `notes <text>` | Add an investigator note to the current case |
| `export` | Export the current case as an HTML report |
| `help` | Show all commands |
| `exit` | Leave |

Or type anything freely — Joe answers questions about the current investigation with full session memory.

---

## How It Works
```
Input (email / domain / IP / username / name)
    ↓
Input Parser — classifies and normalises target
    ↓
Orchestrator — routes to appropriate module pipeline
    ↓
┌─────────────────────────────────────────────┐
│  Sherlock · Maigret · python-whois          │
│  dnspython · crt.sh scraper · nmap          │
└─────────────────────────────────────────────┘
    ↓
Correlation Engine — links entities, scores risk
    ↓
Joe Voice (Ollama + Mistral 7B)
  — inline quote per finding
  — closing monologue after full scan
    ↓
Case File (JSON) + HTML Report
```

---

## Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Terminal UI | Rich |
| Desktop UI | PyWebView |
| Local LLM | Ollama + mistral:7b-instruct |
| Username enum | Sherlock, Maigret |
| Domain intel | dnspython, python-whois, crt.sh |
| Case storage | Local JSON |

---

## Project Structure
```
joe-goldberg/
├── joe.py                  # Entry point — CLI vs desktop detection
├── setup.py                # Package registration
├── install.sh              # Linux/macOS installer
├── install.bat             # Windows installer
├── config.yaml             # Model and tool configuration
├── assets/
│   └── joe.jpeg            # Interface background image
├── cases/                  # Investigation case files (auto-created)
├── core/
│   ├── input_parser.py     # Target type classification
│   ├── target_model.py     # Data structures + case persistence
│   └── orchestrator.py     # Investigation pipeline coordinator
├── narrative/
│   ├── joe_voice.py        # Ollama integration + Joe persona
│   └── session_memory.py   # Conversation context manager
├── modules/
│   ├── social_enum.py      # Username enumeration
│   └── domain_intel.py     # Domain, DNS, certificate intelligence
├── frontend/
│   ├── desktop.py          # PyWebView app + Python-JS bridge
│   └── app.html            # Desktop UI
├── tui/
│   └── joe_cli.py          # Terminal CLI interface
└── exporters/
    ├── case_file.py        # JSON export
    └── html_report.py      # HTML report generation
```

---

## Ethical Use

Joe Goldberg is built for authorized security work only — penetration testing engagements, bug bounty programs, CTF challenges, and authorized investigations.

Do not use this tool against individuals or systems without explicit written authorization. The author assumes no responsibility for misuse.

---

## Author

**Sree Danush S** (L4ZZ3RJ0D)

Cybersecurity student · Offensive security builder · CyArt intern

[![GitHub](https://img.shields.io/badge/GitHub-l4zz3rj0d-c0392b?style=flat-square&logo=github)](https://github.com/l4zz3rj0d)
[![TryHackMe](https://img.shields.io/badge/TryHackMe-Top%201%25-e8a020?style=flat-square)](https://tryhackme.com/p/l4zz3rj0d)
[![Medium](https://img.shields.io/badge/Medium-@l4zz3rj0d-c8945a?style=flat-square&logo=medium)](https://medium.com/@l4zz3rj0d)

---

## Related Projects

- [Hellhound](https://github.com/l4zz3rj0d/Hellhound-Pentest) — modular penetration testing framework

---

<div align="center">
  <sub>Built with obsession. Like Joe would.</sub>
</div>