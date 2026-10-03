# MAC-OUT

**MAC Address Management & Network Identity Observatory**
Designed for CA-1 - MAKAUT, WB. Made by Arnab Mandal (arnabmandal.com, arnab@ik.me).
Special thanks to Dr. Nabanita Ganguly.

MAC-OUT is a desktop app for Linux that sits on top of the `macchanger` command. It does not
reimplement MAC changing. `macchanger` does that. MAC-OUT adds a GUI, checks that every change
really happened, watches what the network does afterwards, and keeps a record you can export.

## What it does

- Lists interfaces with current MAC, permanent MAC (when the driver exposes it), state, IPs, gateway,
  Wi-Fi SSID/BSSID/signal, NetworkManager state.
- Randomize, locally administered, vendor-specific (searchable vendor list with 12 selectable synthetic MAC candidates), specific MAC, restore.
- Every change is request, execute, read back, compare. If the interface reports a different MAC than
  requested, MAC-OUT restores the old one and says so.
- After a change: renews DHCP, waits for the address to come back, runs DNS and Internet checks, and
  shows a before / after comparison with a plain-language result.
- Profiles (Home, Work, Privacy, Testing and your own) with import and export.
- Rotation on a timer and on events (Wi-Fi reconnect, NetworkManager reconnect, interface restart,
  resume, app start), with countdown, pause, manual rotate and a minimum-interval safeguard.
- Persistence: temporary or persistent, with an honest explanation of the mechanism used.
- Event timeline, session recording with summary, structured logs, history with retention.
- Diagnostics wizard with suggested fixes.
- Reports in TXT, JSON, CSV, HTML and ZIP, with privacy redaction.
- Light and dark themes, keyboard navigation, status shown in words as well as colour.

## Requirements

- Linux, target: Debian, Ubuntu, Linux Mint and derivatives, on x86_64 or aarch64 (ARM64).
  Actually tested so far: Ubuntu 22.04 on x86_64 only. ARM64 and the other distributions are untested.
- `python3` (3.8 or newer, tested on 3.10) and GTK 3 bindings: `sudo apt install python3-gi gir1.2-gtk-3.0`
- `macchanger`: `sudo apt install macchanger`
- `iproute2` (already on almost every system)
- Optional: NetworkManager, `iw`, `ethtool`

## Run

```bash
sudo chmod +x macout
sudo ./macout
```

Without `sudo` it still opens, in read-only mode. See INSTALL.md for the single-file build and
TROUBLESHOOTING.md if the window does not open under `sudo`.

## Architectures

`macout` is Python, so there is no compiled code and nothing is x86-specific. The same file runs on
x86_64 and aarch64 when the requirements above are installed. `build.sh` produces `macout-x86_64` and
`macout-arm64`, which are the same file under two labels. They exist so release names are clear. Do not
read that as separately compiled binaries.

## Limitations

- MAC-OUT reports what this computer can observe. It cannot see what your router, ISP or a campus
  access-control system records. The Network Observer says "observed network behavior" for that reason.
- Some drivers and virtual interfaces refuse MAC changes. Some Wi-Fi drivers need the interface down,
  which MAC-OUT handles, and some do not allow a change at all.
- Persistence is only as strong as the network stack. NetworkManager is covered for reboot, reconnect
  and resume on the one connection profile. Without NetworkManager a systemd unit re-applies the MAC at
  boot only.
- Changing MAC addresses on networks you do not own or have permission to use can break their rules.
  Use it on your own equipment and in lab settings.

## Privacy

Everything stays on your machine, in `/var/lib/macout` (root) or `~/.local/share/macout`. Files are
owner-only. Logs and history hold MAC addresses and interface names. Retention is set in Settings.
Reports are redacted by default (IPs, BSSID, SSID, MACs, system info). MAC-OUT makes no network
requests except the local connectivity checks listed in SECURITY.md.

## Tests

```bash
python3 -W ignore -m unittest discover -s tests
```

The core logic runs against a mock backend. `tests/run_gui_demo.sh` runs the real GUI and real
`macchanger` on a dummy interface inside a private user and network namespace, so no real network card
is touched.

### Updated in 1.1.0

Dark by default, selectable vendor MAC series, vendor labels beside displayed addresses, and sudo-safe report exports with desktop-user ownership. See CHANGELOG.md and USAGE.md. The source launcher needs the whole project next to it; for a single-file download use the release asset `macout` built from `dist/macout`.

Release 1.1.0 screenshot set: all 12 dark-themed pages rendered from the shipped zipapp on Ubuntu GTK/Xvfb. Functional report/vendor screenshots are also included.
