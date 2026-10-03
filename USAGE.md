# Using MAC-OUT

1. Start with `sudo ./macout`. The first launch shows a welcome screen and an environment check.
2. Pick the interface in the top left. Everything acts on that interface.
3. **MAC Control**: Randomize, Locally administered, Specific MAC (type it, the hint tells you if it is valid),
   Vendor-specific (search, pick, Generate preview, Apply), or Restore.
   A confirmation appears first because the connection drops for a few seconds.
4. The result card shows requested versus observed MAC. **Network Observer** shows the before / after
   comparison and a plain sentence such as "Network connectivity restored in 2.4 seconds."
   If DHCP did not come back it says so and what to do.
5. **Rotation**: choose an interval (or type minutes), strategy and event triggers, then Start. The countdown
   shows the next rotation. Pause, Rotate now and Stop are next to it. Interval below the safeguard minimum
   (Settings > Rotation, default 1 minute) is refused.
6. **Profiles**: edit, Save, then "Activate on interface". Activating applies the strategy, turns rotation on if the
   profile has it, and makes the MAC persistent if the profile asks for it.
7. **Persistence** (MAC Control page): "Make current MAC persistent" explains the mechanism first. It needs root.
8. **Network Observer > Start Recording** records a session. Stop shows the summary.
9. **Diagnostics**: run the checks. Each problem has a suggested action. Advanced details expand.
10. **Reports**: tick what to redact, choose a format, Export. The text under the checkboxes says what is removed.

## Rotation strategies

| Strategy | What it makes |
|---|---|
| Random | `macchanger -r` picks the address |
| Vendor-specific | OUI you choose plus three random bytes |
| Locally administered | Random unicast address with the local bit set |
| Custom pattern | e.g. `02:xx:xx:xx:xx:xx`, each x is a random hex digit |

## Command line

```
./macout --version
./macout --check
sudo ./macout --apply-persistent    # used by the systemd unit at boot
```

## 1.1.0: vendor series and reports

On MAC Control, search for a vendor and select it on the left. Twelve synthetic MAC candidates appear on the right, covering its usable known prefixes. Select the exact MAC to apply, or choose Generate new series. These are generated addresses, not a list of real devices. A known vendor is shown in brackets beside observed MACs; locally administered values are labeled separately.

Reports now save privately as your invoking desktop user even under sudo. Save to Downloads or another folder you can access. Use Open report or Show folder after export. Re-export any report made by 1.0.0: older files may still be root-owned, and the update deliberately does not change their permissions.

To use your own vendor text file without bundling it, launch with an absolute path:

```sh
sudo env MACOUT_OUI=/absolute/path/mac-vendor.txt ./macout
```

Supported lines: `001122 Vendor name`, macchanger's `00 11 22 Vendor name`, or IEEE's `001122 (base 16) Vendor name`. The user-suggested gist at https://gist.github.com/aallan/b4bb86db86079509e6159810ae9bd3e4 contains prefixes rather than device MACs; it is not bundled because its license was not clear.

The first 1.1.0 launch sets the dark theme. Subsequent choices are saved; Light remains available.
