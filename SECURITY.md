# Security notes

- Runs as root when started with `sudo ./macout`, which is the intended use. Without root it is read-only.
- Commands are started with argument lists. There is no shell and no user-typed command field.
- User input (MAC, OUI, pattern, interface, interval, profile fields) is validated before use.
- Settings, history, logs, profiles and reports are written with mode 0600 inside a 0700 folder.
  Files are written to a temporary name and renamed, so a crash does not leave half-written JSON.
- MAC-OUT never downloads or installs software. If macchanger is missing it tells you the apt command.
- Network activity: a DNS lookup of example.com, a ping to your default gateway, a TCP connect to 1.1.1.1:443
  and, when you have a global IPv6 address, to Cloudflare's IPv6 resolver on 443. Nothing is sent beyond the
  connection attempt. There is no scanning or probing of other hosts.
- Persistence changes system configuration (a NetworkManager connection property or one systemd unit). It asks
  first and can be removed from the app.
- Reports are redacted by default. Check the text under the checkboxes before sharing. Redaction is by value
  and by pattern, so unusual formats may slip through. Read a report before you send it.
- Logs and history contain MAC addresses. Set retention in Settings or delete the data folder.

Report problems to arnab@ik.me.
