# Architecture

```
GUI (gui.py, pages1-3.py, gui_common.py)        GTK 3, no commands run here
 |
Application services (services.py)
 |   MacManager   ProfileManager   RotationEngine   Observer
 |   run_diagnostics   EventLog   History   SessionRecorder
 |   Persistence   ReportGenerator   Settings        <- App wires them together
 |
System abstraction (backend.py)                  the only place that runs commands
 |   macchanger | iproute2 (ip) | NetworkManager (nmcli) | iw | ping | sysfs
 |
Pure helpers (core.py)                           MAC parsing, OUI database, environment detection
```

## Rules the code follows

- **One place for commands.** Only `backend.py` starts processes. It always passes an argument list, never a
  shell string. Interface names must match `^[A-Za-z0-9_.:-]{1,15}$` and not start with `-`. MACs go through
  `normalize_mac` first.
- **Request, execute, verify, report.** `MacManager.apply` snapshots the interface, runs macchanger, reads
  `/sys/class/net/<if>/address`, compares, and recovers the old MAC on mismatch. It then renews DHCP, waits for an
  address, runs connectivity checks, snapshots again and writes history.
- **No fake data.** Every value shown comes from the kernel, `ip`, `macchanger`, `iw` or `nmcli`. If a value is not
  available the UI says "not exposed by driver" or "not tested".
- **GUI never blocks.** Slow calls run in worker threads and return through `GLib.idle_add`.
- **Testable core.** `RotationState` takes a clock. `tests/mock_backend.py` replaces the backend for unit tests.

## Threads

GUI thread, one rotation thread (1 s tick, also watches link events), short-lived worker threads per operation.
`MacManager.apply` holds a lock so two changes never overlap.

## Files on disk

`settings.json`, `history.jsonl`, `profiles/*.json`, `sessions/*.json`, `logs/macout.jsonl`,
`originals.json` (first MAC seen per interface, for drivers with no permanent MAC), `persistent.json`.
All created with owner-only permissions.

## Packaging

`build.sh` creates a Python zipapp. `launcher.py` is the entry point for both `./macout` and the zipapp.
