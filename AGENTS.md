# 当前双模组开发约定

本分支上游来源记录在 upstream.lock.json，初始基线 d4271d46f40bca215d2fba966b83051a1a4460be；ESP-IDF 始终固定 5.5.5。上游更新必须通过 dev_doc/upstream_sync.md 的提醒及人工批准流程，不自动合并、升级 SDK 或烧录。不得迁入旧本地工程源码或配置。保留上游组件位置，双卡接口显式携带 IdfModemId (1/2)，禁止全局当前卡。引脚集中在 idf_board。旧工程必须在实机验收通过后才能清理；设备计费短信需另行明确授权。下方上游说明与双卡实现冲突时以上述约定和 dev_doc/upstream_dual_modem.md 为准。

# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What This Is

ESP32-C3 firmware for a low-cost SMS forwarder. A 4G/LTE modem (ML307R-DC) receives SMS over UART/AT; the ESP32-C3 decodes PDU, then forwards the message over WiFi to email (SMTP) and up to 5 simultaneous push channels, and serves a web UI for config/diagnostics.

The firmware is now native **ESP-IDF only**. The former Arduino fallback sketch has been removed. Keep inline docs/comments in Chinese when editing source files.

## Build / Flash / Monitor

Local ESP-IDF helper:

```powershell
powershell -ExecutionPolicy Bypass -File tools\idf.ps1 build
powershell -ExecutionPolicy Bypass -File tools\idf.ps1 flash -Port COM5
powershell -ExecutionPolicy Bypass -File tools\idf.ps1 monitor -Port COM5
```

The helper loads ESP-IDF 5.5.5, applies the repository-managed Mbed TLS compatibility patch at `patches/idf5.5.5/`, uses Ninja parallelism, and writes generated files to `build/idf5.5.5` with configuration at `build/sdkconfig.idf5.5.5`.

Required ESP-IDF: **v5.5.5**. The firmware targets this SDK's native Mbed TLS 3.6.6. Do not use IDF 6.x headers, binaries, patches or build caches. CI uses the fixed `espressif/idf:v5.5.5` image and applies the same patch after checking that its source context applies cleanly.

For direct Linux `idf.py` use, load the fixed SDK and apply the repository patch first:

```bash
. "$IDF_PATH/export.sh"
python tools/apply_idf_patches.py --idf-path "$IDF_PATH"
```

Before committing Web UI changes, run:

```powershell
python tools\build_web_assets.py
python tools\build_web_assets.py --check
```

CI builds the ESP-IDF firmware via `.github/workflows/build.yml`.

## Architecture

Project entrypoints:

- `CMakeLists.txt`, `main/`, and `components/` are the ESP-IDF firmware.
- `components/idf_modem` owns UART1 and all modem AT traffic.
- `components/idf_sms` handles PDU SMS receive/send, SIM storage polling, multipart merge, dedup, blacklist/admin commands, and enqueueing forwards.
- `components/idf_push` owns HTTP/HTTPS push, SMTP, forward queues, retry queues, test push, and forward-rule evaluation.
- `components/idf_web` owns `esp_http_server`, all Web/API routes, scheduler, keep-alive jobs, OTA upload, diagnostics, and status JSON.
- `components/idf_wifi` owns STA/SoftAP provisioning, captive DNS, lightweight mDNS, SNTP, reconnect watchdog, and BOOT long-press provisioning.
- `components/idf_config` persists config in NVS namespace `sms_config`; old NVS keys remain additive/compatible.
- `components/web_assets` links generated gzip Web assets from `code/web_assets.cpp`; editable sources live in `code/web_src/`.

Slow work must stay off request handlers where possible: use existing worker queues for push/email/modem/keep-alive work so SMS receive and Web refresh stay responsive.

## Web UI Assets

Editable UI files live in `code/web_src/`:

- `index.html`
- `app.css`
- `app.js`
- `panels/*.html`

Generated assets are `code/web_assets.h` and `code/web_assets.cpp`. Do not hand-edit generated assets; run `python tools/build_web_assets.py` after editing `web_src`.

New page placeholder flow: add `%TOKEN%` in a panel, render it in `code/web_src/app.js`, expose any dynamic value from `/config.json`, then regenerate assets.

## Extension Conventions

- **New push channel**: add type handling in `components/idf_push/idf_push.cpp`, add validation, then add the Web UI option and hint in `code/web_src/app.js`. `IDF_MAX_PUSH_CHANNELS` is 5.
- **New config field**: add to `IdfConfig`, load/save it in `components/idf_config/idf_config.cpp`, expose/parse it in Web config handlers, and keep the key additive with a default.
- **New HTTP route**: add a handler in `components/idf_web/idf_web.cpp`, register it in `idf_web_start()`, and prefer bounded/streaming responses over large one-shot strings.
- **Logging**: use `idf_log_line()` / `idf_logf()` for Web-visible logs. Logs are mirrored into the 120-entry ring buffer.
- **Privacy**: SMS body and phone numbers should remain masked in normal logs; full content belongs only behind explicit verbose/debug builds.
- **Modem order matters**: handshake, disable/enable data per config via `CGACT`, configure storage/CNMI/PDU mode, then wait for CEREG. PDU mode is required for Chinese SMS.
- **Receive robustness**: keep both URC receive and periodic `AT+CMGL` storage polling. Dedup makes the dual path safe.
