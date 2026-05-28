# WDAP OTA Host Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first usable WDAP OTA host tool for Windows-first development, with a testable protocol core, firmware package parser, resumable OTA session logic, and a PySide6 GUI shell.

**Architecture:** First build a pure-Python protocol core that can be tested without hardware: frame codec, firmware package parser, mock serial transport, and OTA session state machine. Then add a CLI for hardware bring-up, and only after the protocol is stable add the PySide6 UI that calls the same session APIs. OTA is always carried by the management channel, never by the user wireless UART channel.

**Tech Stack:** Python 3.11+, pytest, pyserial, PySide6, struct/hashlib/zlib, optional PyInstaller for packaging.

---

## Current Scope

| Version | What It Does |
|---|---|
| First version | Python package under `tools/wdap_ota`, frame encode/decode, `.wdapfw` parse/check, mock transport, CLI `hello/info/query/upload`, basic PySide6 GUI shell |
| Not in first version | Real firmware flashing against hardware without firmware support, bitmap missing-block recovery, signature verification, Tauri/Rust production UI |

## Future Optimization Direction

| Area | First Version | Later Replacement / Upgrade |
|---|---|---|
| UI framework | PySide6 | Tauri + Rust + Web UI when protocol is stable and productization matters |
| Transport | CDC1 management serial via pyserial | USB Vendor/Bulk or WinUSB for higher throughput |
| Resume | Sequential `next_offset` | Bitmap missing-block recovery and sliding window ACK |
| Integrity | CRC32 per chunk + SHA256 full image | Signed firmware package with Ed25519 or ECDSA |
| Protocol implementation | Python dataclasses and struct | Shared schema/codegen for Python, CH32 C, ESP C |
| Packaging | PyInstaller/Nuitka | Signed Windows installer and auto-update |

## Non-Negotiable Protocol Boundary

| Rule | Reason |
|---|---|
| OTA host only talks to `CDC1_MGMT` | User UART bytes must never be parsed as OTA |
| User serial terminal uses `CDC0_USER_UART` | Binary user traffic stays pure UART data |
| OTA requires `magic + type + session_id + state` | Prevents random bytes or old packets from writing Flash |
| `OTA_COMMIT` is explicit | Finished transfer does not automatically enable firmware |

## Planned File Layout

```text
tools/wdap_ota/
  pyproject.toml
  README.md
  src/wdap_ota/
    __init__.py
    cli.py
    protocol/
      __init__.py
      constants.py
      crc.py
      frame.py
      firmware.py
    transport/
      __init__.py
      base.py
      mock.py
      serial_port.py
    ota/
      __init__.py
      session.py
      state.py
    gui/
      __init__.py
      app.py
      main_window.py
  tests/
    test_frame.py
    test_firmware.py
    test_ota_session.py
```

### Task 1: Project Skeleton

**Files:**
- Create: `tools/wdap_ota/pyproject.toml`
- Create: `tools/wdap_ota/README.md`
- Create: `tools/wdap_ota/src/wdap_ota/__init__.py`
- Create package `__init__.py` files under `protocol`, `transport`, `ota`, `gui`

**Step 1: Create package metadata**

Use `setuptools` with dependencies:

```toml
[project]
name = "wdap-ota"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "pyserial>=3.5",
  "PySide6>=6.7",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
wdap-ota = "wdap_ota.cli:main"
wdap-ota-gui = "wdap_ota.gui.app:main"
```

**Step 2: Add README**

Document what the tool currently does and that the first version uses `CDC1_MGMT`, not the user UART.

**Step 3: Verify import package**

Run:

```powershell
cd tools/wdap_ota
python -m pip install -e .[dev]
python -c "import wdap_ota; print(wdap_ota.__version__)"
```

Expected: prints `0.1.0`.

### Task 2: Frame Codec TDD

**Files:**
- Create: `tools/wdap_ota/tests/test_frame.py`
- Create: `tools/wdap_ota/src/wdap_ota/protocol/constants.py`
- Create: `tools/wdap_ota/src/wdap_ota/protocol/crc.py`
- Create: `tools/wdap_ota/src/wdap_ota/protocol/frame.py`

**Step 1: Write failing tests**

Test:
- `HostFrame.HEADER_SIZE == 28`
- Encoding prepends SOF `55 AA`
- Decoding validates magic, length, header CRC, payload CRC
- Corrupt payload raises `FrameDecodeError`

**Step 2: Run failing test**

Run:

```powershell
cd tools/wdap_ota
pytest tests/test_frame.py -v
```

Expected: FAIL because modules do not exist.

**Step 3: Implement minimal frame codec**

Implement:
- `FrameType`, `Target`, `FrameFlags`
- `crc16_ccitt(data: bytes) -> int`
- `crc32(data: bytes) -> int`
- `HostFrame.encode() -> bytes`
- `HostFrame.decode(packet: bytes) -> HostFrame`
- `FrameDecodeError`

**Step 4: Verify**

Run:

```powershell
cd tools/wdap_ota
pytest tests/test_frame.py -v
```

Expected: PASS.

### Task 3: Firmware Package Parser TDD

**Files:**
- Create: `tools/wdap_ota/tests/test_firmware.py`
- Create: `tools/wdap_ota/src/wdap_ota/protocol/firmware.py`

**Step 1: Write failing tests**

Test:
- Valid `.wdapfw` bytes parse into header and payload
- `magic != WDAPFW` fails
- CRC mismatch fails
- SHA256 mismatch fails

**Step 2: Run failing test**

Run:

```powershell
cd tools/wdap_ota
pytest tests/test_firmware.py -v
```

Expected: FAIL because parser does not exist.

**Step 3: Implement minimal parser**

Implement:
- `FirmwarePackage.from_bytes(data: bytes)`
- `FirmwareHeader`
- `FirmwareParseError`
- `is_compatible(target_chip, hardware_rev, role)`

**Step 4: Verify**

Run:

```powershell
cd tools/wdap_ota
pytest tests/test_firmware.py -v
```

Expected: PASS.

### Task 4: Mock Transport and OTA Session TDD

**Files:**
- Create: `tools/wdap_ota/tests/test_ota_session.py`
- Create: `tools/wdap_ota/src/wdap_ota/transport/base.py`
- Create: `tools/wdap_ota/src/wdap_ota/transport/mock.py`
- Create: `tools/wdap_ota/src/wdap_ota/ota/state.py`
- Create: `tools/wdap_ota/src/wdap_ota/ota/session.py`

**Step 1: Write failing tests**

Test:
- `hello()` sends `HELLO` and parses `HELLO_RSP`
- `query_resume()` returns `next_offset`
- `upload()` starts from `next_offset`
- offset mismatch raises recoverable error

**Step 2: Run failing test**

Run:

```powershell
cd tools/wdap_ota
pytest tests/test_ota_session.py -v
```

Expected: FAIL because session/transport modules do not exist.

**Step 3: Implement minimal session**

Implement:
- `Transport` protocol with `write_frame` and `read_frame`
- `MockTransport`
- `OtaSession.hello()`
- `OtaSession.query_resume()`
- `OtaSession.upload_bytes()`

**Step 4: Verify**

Run:

```powershell
cd tools/wdap_ota
pytest tests/test_ota_session.py -v
```

Expected: PASS.

### Task 5: CLI Shell

**Files:**
- Create: `tools/wdap_ota/src/wdap_ota/cli.py`
- Modify: `tools/wdap_ota/README.md`

**Step 1: Add CLI commands**

Commands:

```text
wdap-ota hello --port COMx
wdap-ota info --port COMx
wdap-ota parse firmware.wdapfw
wdap-ota upload --port COMx --target LOCAL_CH32 firmware.wdapfw --resume
```

**Step 2: Add serial transport**

Create `tools/wdap_ota/src/wdap_ota/transport/serial_port.py`.

**Step 3: Verify parse command without hardware**

Run:

```powershell
cd tools/wdap_ota
python -m wdap_ota.cli --help
```

Expected: shows command help.

### Task 6: PySide6 GUI Shell

**Files:**
- Create: `tools/wdap_ota/src/wdap_ota/gui/app.py`
- Create: `tools/wdap_ota/src/wdap_ota/gui/main_window.py`

**Step 1: Build shell UI**

UI regions:
- COM selector, refresh, connect
- target selector
- firmware file chooser
- package info table
- progress bar and status fields
- log output
- start/pause/resume/cancel buttons

**Step 2: Keep UI passive**

The UI must call `OtaSession`; it must not build frames directly.

**Step 3: Verify launch**

Run:

```powershell
cd tools/wdap_ota
python -m wdap_ota.gui.app
```

Expected: desktop window opens.

### Task 7: Full Verification

**Files:**
- Modify as needed under `tools/wdap_ota`

**Step 1: Run all tests**

```powershell
cd tools/wdap_ota
pytest -v
```

Expected: all tests pass.

**Step 2: Run import and CLI checks**

```powershell
cd tools/wdap_ota
python -c "import wdap_ota; print(wdap_ota.__version__)"
python -m wdap_ota.cli --help
```

Expected: version and CLI help print.

**Step 3: Report remaining hardware gaps**

Document that real OTA requires firmware-side `CDC1_MGMT` protocol implementation.
