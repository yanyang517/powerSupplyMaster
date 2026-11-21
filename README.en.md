# powerSupplyMaster

**English** | [中文](README.md)

A PC-side control station for SCPI-programmable DC power supplies — with a PySide6 GUI, a TCP/JSON control server, and an MCP bridge that lets AI assistants operate the hardware safely.

Connect over serial (pyserial) to any SCPI-speaking bench supply (developed against RIGOL DP832-class instruments), then control it from the desktop UI, from remote programs over TCP, or from an AI client such as Qoder Desktop / Claude Desktop.

## Features

- **Desktop GUI (PySide6)** — serial port picker, voltage dial + spinbox linkage, output on/off, live voltage/current charts, always-on-top floating mini-window, dark theme, window geometry memory.
- **TCP/JSON control server** — listens on `:18888`, length-prefixed UTF-8 JSON frames; remote programs can query and set voltage/current/output through the same device session.
- **MCP server for AI control** — stdio MCP bridge exposing `get_status` / `set_voltage` / `set_current` / `set_output`, so an LLM agent can read and drive the supply with the same safety limits as the GUI.
- **Shared safety limits** — `--max-voltage` / `--max-current` are enforced server-side and apply uniformly to GUI, TCP clients, and AI.
- **Device simulator** — a standalone SCPI simulator process (with virtual serial ports) for development and integration testing without hardware.
- **Headless mode** — `--no-gui` runs the control server alone.
- **Version identity and update notice** — the version is defined once in `src/version.py` and surfaced in the window title, About page, startup log, exe file properties and the `setting_query`/MCP responses. A background check reads the `update/latest.json` manifest and only shows a status-bar notice — it never downloads or replaces anything (skipped with `--no-update-check` or `--no-gui`). See [doc/version_info.md](doc/version_info.md) and [doc/update_notice.md](doc/update_notice.md).
- **Icons and app identity** — UI icons are vendored open-source line glyphs (Tabler 3.52.0 / MIT, Lucide 1.77.0 / ISC, 18 files), recolored from theme tokens with size-tiered stroke weights; a missing glyph degrades to no icon instead of breaking startup. The app mark is an original solid squircle with a knocked-out power symbol, and both the window icon and the exe's `app.ico` derive from that one SVG (`scripts/gen_icon.py`). Provenance, versions and placement are listed in [src/resources/NOTICE.md](src/resources/NOTICE.md).

## Architecture

```
┌──────────────┐      serial (SCPI)      ┌──────────────────┐
│ PySide6 GUI  │ ─────────────────────── │  DC Power Supply │
└──────┬───────┘                         └──────────────────┘
       │ qasync (single Qt + asyncio loop)
       │
┌──────┴───────┐   TCP JSON (4-byte length + UTF-8)  ┌─────────────┐
│ app.py       │ ◄────────────────────────────────── │ TCP clients │
│ + server     │                                      └─────────────┘
└──────┬───────┘
       │ stdio MCP
┌──────┴───────┐
│ MCP bridge   │ ← AI clients (Qoder Desktop, Claude Desktop, ...)
└──────────────┘
```

Single-process design: GUI and asyncio server share one event loop via [qasync](https://github.com/CQFDotIO/qasync). The SCPI driver is a process-level singleton, so every control path (GUI / TCP / MCP) goes through one serial session and one transaction lock.

## Quick start

Requires Python ≥ 3.10 (Windows is the primary target; the GUI/server code itself is cross-platform).

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # Linux/macOS

# GUI mode (pick the COM port in the UI, press Connect)
.venv/Scripts/python.exe src/app.py

# Headless server only, listens on 0.0.0.0:18888
.venv/Scripts/python.exe src/app.py --no-gui

# Configure safety limits (defaults: 30 V / 5 A)
.venv/Scripts/python.exe src/app.py --max-voltage 24 --max-current 3
```

> Note: imports are rooted at `src/`, so run from the repo root with the paths above (or `cd src` and run `python app.py`).

### No hardware? Use the simulator

Create a virtual serial pair (e.g. [com0com](https://com0com.sourceforge.net/) → `COM8 ↔ COM9`), then:

```bash
# terminal 1 — simulate the power supply on COM9
python src/device/device_simulator.py --port COM9 --baud 115200

# terminal 2 — run the app, select COM8 in the UI
python src/app.py
```

## AI control via MCP

The bundled MCP server lets an AI client read and drive the supply through natural language. Serial ownership stays with the desktop app — the AI can only use what the transport schema allows, and limit violations are rejected server-side.

1. Run `powerSupplyMaster` (GUI or `--no-gui`) so the TCP server is listening.
2. Connect the serial port in the UI once.
3. Install the bridge package `psu-mcp` (offline wheel basket: see [doc/mcp_integration.md](doc/mcp_integration.md); repo developers: `pip install -e packages/psu-mcp`).
4. Add to your MCP client config:

```json
{
  "mcpServers": {
    "power-supply": {
      "command": "psu-mcp"
    }
  }
}
```

Available tools:

| Tool | Arguments | Description |
|---|---|---|
| `get_status` | — | Voltage, current, output state, device ID, active `limits` (incl. the host app version as `limits.server_version`) |
| `set_voltage` | `voltage` (V) | Rejected with guidance if outside `limits.max_voltage_v` |
| `set_current` | `current` (A) | Rejected if outside `limits.max_current_a` |
| `set_output` | `enable` (bool) | Switch the output on/off |

More details: [doc/mcp_integration.md](doc/mcp_integration.md).

## TCP protocol

Frame format: `uint32BE payload length | UTF-8 JSON`, one request → one response, on port **18888**.

Request fields: `type` (discriminator), `request_id`, `timestamp`, plus command-specific parameters. Supported types include `echo`, `login`/`logout`, `open_device`/`close_device`, `set_voltage`, `set_current`, `set_on_off`, `voltage_query`, `current_query`, `on_off_query`, `device_id_query`, `setting_query` (its response carries the active limits and the host app version). See [src/server/protocal/protocal.py](src/server/protocal/protocal.py) for the schema (contract) definitions and a client example in [src/server/test_client.py](src/server/test_client.py).

## Build a Windows executable

```powershell
# needs .venv at the repo root; output lands in dist/
powershell -File scripts/build_exe.ps1
```

A GitHub Actions workflow ([.github/workflows/release.yml](.github/workflows/release.yml)) builds and publishes the exe on `v*` tags.

## Project layout

```
src/
├── app.py              # entry point (GUI + server in one loop)
├── version.py          # the single definition of the app version
├── presenter/          # MVP: presentation logic + periodic sampling
├── views/              # PySide6 UI (main window, floating window, dark theme, update notice)
├── device/             # SCPI serial driver (singleton) + device simulator
├── server/             # TCP/JSON socket server, dispatcher, request schema
├── mcp_server/         # wire-protocol regression tests for the bridge (code moved to packages/psu-mcp)
└── update/             # update probing: manifest, comparison, state, scheduler
update/latest.json      # published release manifest (same file on Gitee and GitHub)
doc/                    # architecture docs, MCP integration guide
scripts/                # PyInstaller build script, manifest generation and checks
```

## Testing

Integration tests (a running server + a real or virtual COM port) live next to the server code:

```bash
cd src
python -m pytest server/test_client.py -v
```

## Known limitations

- GUI and remote TCP/AI paths share one serial session without an ownership arbitration layer yet — concurrent control from multiple paths is possible but not coordinated.
- Write commands (`VOLT`, `OUTP`) do not read device error queues back, so device-side errors are silent to the operator.
- Some protocol types are declared without handlers, and the test suite requires real hardware/virtual ports.

Contributions to fix these are welcome — see the issue tracker.

## License

Released under the GNU Lesser General Public License v3.0 (LGPL-3.0). See [LICENSE](LICENSE).
