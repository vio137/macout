# Troubleshooting

**The window does not open with sudo.** sudo can drop your display permissions. Try `sudo -E ./macout`. On an X
desktop you can also run `xhost +si:localuser:root` once, then `sudo ./macout`. MAC-OUT already tries to borrow
`~/.Xauthority` of the user who ran sudo. On Wayland, `sudo -E` normally works.

**"MAC-OUT needs GTK 3 for Python".** `sudo apt install python3-gi gir1.2-gtk-3.0`.

**macchanger is missing.** `sudo apt install macchanger`. Run `./macout --check` to see what was found.

**"Operation not permitted" or the app is read-only.** You are not root. Start with `sudo ./macout`.

**macchanger fails with "Cannot set MAC".** The driver or interface refuses changes. Virtual, tunnel and some
Wi-Fi interfaces do. MAC-OUT leaves the old MAC in place and logs the error.

**MAC changed but no connection afterwards.** The result card says so. MAC-OUT already asks NetworkManager (or networkd/dhclient) to renew
the lease. If that did not work, reconnect the interface from your network menu. Some access points remember a MAC and delay a new one. Wait 30 seconds and run
Diagnostics.

**Permanent MAC shows "not exposed by driver".** Many virtual and some USB interfaces do not report one. MAC-OUT
remembers the first MAC it ever saw on that interface and restores to that.

**Persistence without NetworkManager does not survive reconnects.** Correct. The systemd unit only runs at boot.

**macchanger asks about boot-time changes during install.** Answer No. MAC-OUT handles changes itself.

### Report says permission denied or cannot be found

Version 1.0.0 could create root-owned private reports when launched with sudo and start the save dialog in root's folders. Update to 1.1.0, then export again to your own Downloads folder. New reports are 0600 and owned by the validated SUDO_USER. We do not make diagnostic reports world-readable. Open report uses your desktop identity; if your desktop's xdg-open association is missing or its session cannot be reached, the saved path is shown so you can open it with your file manager.
