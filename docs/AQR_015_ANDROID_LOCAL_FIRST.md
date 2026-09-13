# AQR-015 — Android local-first candidate

## Purpose

The Android package is a shell around the same canonical Aqorath V1 authority. It is **not** a client for a Meriadock service and it does not introduce a second accounting engine, ledger, persistence authority or fiscal authority.

## Data ownership boundary

For Android, Aqorath stores its active SQLite database under the application's private `filesDir` sandbox:

`filesDir/aqorath/aqorath.db`

The app does not configure a Meriadock backend, user account, telemetry collector, remote backup service or synchronization endpoint. Android backup is disabled for this candidate so the OS does not silently replicate Aqorath application data through the application's backup declaration.

User-directed backup/export remains the portability mechanism. A later Android file-picker surface may make transfer more convenient, but transfer must remain an explicit user act rather than hidden synchronization.

## Network boundary

The Android process requires the Android `INTERNET` permission only because the native WebView talks to the canonical Aqorath HTTP surface on `127.0.0.1` inside the same device.

Containment is layered:

1. Python installs a process-wide socket/DNS guard before product bootstrap. Non-loopback destinations fail closed.
2. Uvicorn binds only to `127.0.0.1:8765`.
3. The Android WebView accepts and loads only `http` URLs whose host is `127.0.0.1`, `localhost` or `::1`.
4. WebView subresources outside that loopback policy receive a synthetic HTTP 403 response.
5. CI boots the installed APK with Wi-Fi/data disabled and Android airplane mode enabled.

Therefore airplane mode is an acceptance property, not an optional feature.

## Packaging authority

The Android job depends on the Linux AQR-015 build job and consumes the exact `aqorath-0+aqr015-py3-none-any.whl` already subjected to source-tree tests, distribution smoke/hardening and installed V1 acceptance. Chaquopy embeds Python 3.12 and that accepted wheel into the APK.

The mobile shell contains lifecycle and presentation plumbing only. Accounting rules remain in Aqorath Python authorities.

## Candidate acceptance

The Android candidate is technically acceptable only when one workflow run proves all of the following on the same commit:

- Linux source suite green;
- sdist/wheel build green;
- distribution/hardening smoke green;
- `22/22 TECHNICAL_INSTALLED: PASS` on the canonical wheel;
- Android APK builds from that wheel;
- APK installs into a clean Android emulator;
- airplane mode is enabled before application launch;
- application logs `AQORATH_ANDROID_NETWORK_GUARD=loopback-only`;
- WebView loads the canonical local surface and logs `AQORATH_ANDROID_READY`;
- the app-private `aqorath/aqorath.db` exists after bootstrap;
- `/api/capabilities` is reachable only through device loopback (tested through `adb forward`);
- install/run requires no Python, pip, terminal or Meriadock service on the user's phone.

## Status boundary

Passing this Android packaging gate does not by itself change:

- `PROFESSIONAL_REVIEW: PENDING`
- `HUMAN_ACCEPTANCE: PENDING`
- `END_TO_END: NOT YET`

AQR-015 remains the unique `NEXT` until R27 is fully satisfied.
