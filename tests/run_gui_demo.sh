#!/bin/sh
# Real end-to-end demo in a private user+network namespace (no root needed, never touches real NICs).
# Needs: xvfb, macchanger (unpacked to $MC if not installed), python3-gi.
set -e
MC=${MC:-/tmp/mc}
export MACOUT_HOME=${MACOUT_HOME:-/tmp/macout-home}; rm -rf "$MACOUT_HOME"
export DISPLAY=${DISPLAY:-:99}
cd "$(dirname "$0")/.."
unshare -Urnm sh -c '
  if ! command -v macchanger >/dev/null; then
    mount -t overlay -o lowerdir='"$MC"'/usr/share:/usr/share overlay /usr/share
    export PATH='"$MC"'/usr/bin:$PATH MACOUT_OUI='"$MC"'/usr/share/macchanger/OUI.list
  fi
  mount -t sysfs sysfs /sys
  ip link add wlan0 type dummy
  ip link set wlan0 address a4:83:e7:12:34:56
  ip addr add 10.77.0.2/24 dev wlan0
  ip link set wlan0 up
  ip link set lo up
  python3 tests/gui_drive.py
'
