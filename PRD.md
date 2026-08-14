# PRD: Pi Dashboard — Modular Raspberry Pi Data Display

**Author:** Chris | **Date:** 2026-08-13 | **Status:** Draft v1

## 1. Overview

A desk-mounted, always-on dashboard built on a Raspberry Pi 4 that displays multiple independent data modules, each rendered on its own 1.28" round SPI (GC9A01) display. Displays are chained off a shared SPI bus, each addressed via its own chip-select (CS) GPIO pin. The system launches with two modules — Claude API token/cost usage and local weather — and is architected so additional modules can be added later as pure software, without rewiring, as long as spare CS pins are wired up front.

## 2. Goals

- Modular architecture: each data module is a self-contained Python service that renders to one physical display; modules can be added, removed, or restarted independently.
- Ship two working modules at launch: Claude usage and local weather.
- Provision wiring for 4–6 displays now, even though only 2 ship at launch, so future modules require no hardware changes.
- Always-on, headless, self-healing: boots directly into dashboard mode and recovers automatically from crashes or power loss.

## 3. Non-Goals (v1)

- No touchscreen input or interactivity — displays are read-only output.
- No mobile app or remote web dashboard (may be a future module).
- No multi-user/multi-account support — single Claude account, single location for weather.
- No historical data storage/analytics beyond what's needed to render the current view (e.g., a simple daily usage trend is fine; a full data warehouse is not).

## 4. Hardware

| Component | Choice | Notes |
|---|---|---|
| Board | Raspberry Pi 4 (2GB+ recommended) | Chosen for headroom to run multiple render loops plus API polling |
| Displays | 1.28" round SPI displays (GC9A01 driver, 240x240) | Chained on one SPI bus |
| Wiring | Shared MOSI/SCK/DC/RST lines; unique CS GPIO per display | Standard approach for multiple SPI displays without a mux; Pi 4 has enough usable GPIO for 4-6 CS lines |
| Power | Single 5V/3A+ USB-C supply for the Pi; displays powered from Pi 3.3V rail | Confirm total display current draw stays within Pi's 3.3V rail budget as more are added |
| Enclosure | Desk-mounted stand/case, always-on | Design open; should route SPI ribbon/wires cleanly to each display bay |
| Storage | microSD (32GB+) or USB SSD boot | USB SSD boot recommended for reliability on an always-on device |

**Open hardware question:** confirm exact GC9A01 display module/vendor so pinout and library (e.g., `luma.lcd`, `Adafruit_CircuitPython_GC9A01`) can be pinned down.

## 5. Software Architecture

- **Language:** Python 3.
- **Structure:** one lightweight "module" per data source, each a Python process/thread responsible for (1) fetching its data on a schedule, (2) rendering a frame (via Pillow), and (3) pushing that frame to its assigned display over SPI.
- **Orchestrator:** a supervisor process (or systemd) starts/monitors each module independently, restarts a crashed module without affecting others, and reads a central config file (`modules.yaml` or similar) mapping each module to its CS pin, refresh interval, and any credentials.
- **Config-driven display mapping:** adding a new module later means writing a new module script and adding one entry to the config — no changes to existing modules.
- **Secrets:** API keys (Anthropic Admin API key, etc.) stored in a local `.env` file or `secrets.yaml`, excluded from version control.
- **Boot behavior:** systemd service starts the orchestrator on boot; auto-restarts on failure; no desktop environment required (headless).

## 6. Module 1: Claude Token Usage

**Scope decision:** use the OAuth-based private usage endpoint that Claude Code's own CLI uses internally to show rate-limit status. This is the approach already proven working in Chris's existing `Waveshare-ePaper-10.85-dashboard` project (`claude.py`), so v1 will adapt that script rather than build from scratch.

- **Data source:** `GET https://api.anthropic.com/api/oauth/usage`, authenticated with an OAuth access token obtained via Claude Code's own public OAuth client ID, header `anthropic-beta: oauth-2025-04-20`. Returns `five_hour.utilization`/`resets_at` and `seven_day.utilization`/`resets_at` — i.e., actual rolling rate-limit percentages, not token counts or dollars.
- **Auth flow:** one-time interactive PKCE OAuth setup (open an authorize URL, log in, paste the callback URL back) produces an access token + refresh token, stored locally (`claude_creds.json`, chmod 600). Subsequent runs auto-refresh the token as needed — no repeated login.
- **Where it runs:** can run directly on the Pi (no dependency on Chris's main machine, unlike the log-sync approach considered earlier) — the Pi just needs outbound HTTPS and the one-time interactive setup performed once from any browser.
- **Display content:** 5-hour utilization % and time-to-reset, plus 7-day utilization % and time-to-reset — rendered as two compact gauges/rings given the round screen.
- **Refresh interval:** every 5–10 minutes (matches the existing script's polling cadence; endpoint doesn't publish a documented rate limit, so avoid polling more aggressively than needed).
- **Failure behavior:** on 401/429/network error, keep showing the last-known value with a stale-data indicator; auto-refresh token on 401 before giving up.
- **Risk — undocumented API:** this endpoint is not publicly documented by Anthropic; it's the same one the Claude Code CLI calls internally. It could change or be revoked without notice. Not a blocker for a personal project, but worth monitoring — if it breaks, fall back to Claude Code local JSONL log parsing (e.g., `ccusage`-style) or the officially documented Admin API (`GET /v1/organizations/usage_report/messages`, org-level API billing usage, requires Admin API key) as a plan B.

## 7. Module 2: Local Weather

- **Data source:** Open-Meteo (free, no API key required).
- **Location:** needs a fixed lat/long or city — **open question:** what location should be hardcoded (home address's approximate coordinates, or a named city)?
- **Display content:** current temperature, condition icon, and optionally a short forecast (e.g., today's high/low).
- **Refresh interval:** every 10–15 minutes (weather doesn't need to be real-time).
- **Failure behavior:** same stale-data pattern as Module 1.

## 8. Future Modules (not built now, architecture must support)

Examples to validate the modular design against: calendar/next-meeting, system stats (Pi CPU/temp/uptime), stock/crypto price, home automation status, RSS/news headline. Each should be addable as a new script + one config entry, using a spare CS pin already wired.

## 9. Non-Functional Requirements

- **Reliability:** target 99%+ uptime over a week of always-on operation; auto-recovery from power loss and crashed modules without manual intervention.
- **Performance:** each display refresh should render in well under its polling interval; no module's rendering loop should block another's.
- **Maintainability:** adding a module should take under ~30 minutes of work for someone comfortable with the codebase (write script, add config entry, wire nothing new since spare pins are pre-provisioned).
- **Security:** API keys never committed to version control; local network only (no exposed ports/services).

## 10. Open Questions (need answers before implementation starts)

1. **Claude usage OAuth setup:** confirm the Pi will have a way to complete the one-time interactive PKCE login (e.g., a browser on another device that can reach `localhost:18924` during setup, or adapting the redirect handling) — needs to happen once during bring-up, not on every boot.
2. **Weather location:** what city/coordinates to hardcode?
3. **Exact display module/vendor:** which GC9A01 product, to confirm pinout and driver library?
4. **Number of displays to physically wire at build time:** 2 now with pins reserved for how many more (4 total? 6 total)?
5. **Boot storage:** microSD vs. USB SSD boot?
6. **Case/enclosure:** off-the-shelf, 3D-printed custom design, or open-frame for now?

## 11. Milestones (proposed)

1. Hardware bring-up: wire 2 displays (with 2-4 spare CS lines reserved), confirm both render test patterns.
2. Orchestrator + config-driven module loading skeleton, running one dummy module.
3. Weather module: fetch + render on real hardware.
4. Claude usage module: adapt existing `claude.py` OAuth usage script from the Waveshare-ePaper project, complete one-time auth on the Pi, render on real hardware.
5. systemd auto-start + crash recovery testing (pull power mid-run, kill a module process).
6. Documentation: how to add a new module.

---

## Resolved during implementation

- **#2 Weather location:** zip 63043 (Maryland Heights, MO) → lat 38.7229, lon -90.4474.
- **#4 Display count:** 6 total (2 wired at launch, 4 spare CS pins reserved).
- **#3 Exact display vendor:** still open — the GC9A01 pinout/init sequence used is the one nearly universal across vendors, but treat it as unverified until `scripts/test_display.py` runs on real hardware (see `docs/WIRING.md`).
- **#5 Boot storage, #6 Enclosure:** still open, don't block software — decide at physical build time.
