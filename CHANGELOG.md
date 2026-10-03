# Changelog

## 1.1.0 - 2026-10-03

- Fix sudo-generated reports: exports are private (0600) but owned by the validated invoking desktop user, including ZIP. Save dialogs start in that user's Downloads folder or home.
- Atomic UTF-8 report writes: failed generation leaves an existing report intact. Add file extensions, clear progress/errors, Open report and Show folder actions. Desktop open runs as the invoking user, not root.
- Vendor chooser generates 12 unique selectable synthetic MACs across a vendor's known OUIs. Picking another vendor or changing search clears stale candidates. No stale-vendor apply.
- Bracketed vendor names beside displayed MACs, including random addresses when their OUI is known. Local addresses are labeled locally administered, not falsely manufacturer-assigned. Machine fields/commands remain raw.
- Dark default for new and upgraded installs, light toggle retained, light logo card, compact identity details, two-panel vendor picker, scrollable tables, wrapped values and shorter window subtitle.
- Support local vendor lists in six-hex-prefix text format, as well as macchanger and ieee-data formats. No unlicensed third-party list is bundled.
- Fix timestamp false positives in IP redaction.
- Regression checks added for save dialogs, export permissions/identity, atomic writes, vendor changes, default dark theme and packaged GUI screenshots.

Tested on Ubuntu 22.04 x86_64 in Xvfb, actual macchanger 1.7.0 on a private dummy network interface; all five export formats via real GTK save dialogs, readable HTML in Chrome. Real GNOME/Xfce sessions, sudo-to-desktop open integration, actual Wi-Fi hardware, ARM64 and boot persistence are not available in this environment and remain unverified.



## 1.0.0
- First release: dashboard, interface list, MAC control with verify-after-change and automatic recovery,
  vendor search, profiles, rotation (timer and events), persistence (NetworkManager or systemd), network
  observer with before/after, diagnostics, session recording, structured logs, history, TXT/JSON/CSV/HTML/ZIP
  reports with redaction, light and dark themes, MAKAUT branding.
- 39 unit tests with a mock backend. Real end-to-end run on a dummy interface with real macchanger.
