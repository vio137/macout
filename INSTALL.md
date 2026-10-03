# Install

## Debian, Ubuntu, Mint (x86_64 and arm64)

```bash
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-3.0 macchanger iproute2
```

During the macchanger install, answer "No" if it asks about changing MACs automatically at boot.

## Get MAC-OUT

Either run from the source folder:

```bash
sudo chmod +x macout
sudo ./macout
```

or build one file and run that:

```bash
./build.sh
sudo ./dist/macout
```

`dist/macout` is a Python zipapp. Copy it anywhere. `sudo install -m 755 dist/macout /usr/local/bin/macout`
puts it on your PATH.

## Check your setup

```bash
./macout --check
```

prints the architecture, distribution and which tools were found. It exits with 2 when `macchanger` is missing.

## Uninstall

Delete the file. User data lives in `/var/lib/macout` or `~/.local/share/macout`. If you used persistence
without NetworkManager, also run `sudo systemctl disable macout-persist.service` and delete
`/etc/systemd/system/macout-persist.service`. MAC-OUT's own "Remove persistence" button does this.
