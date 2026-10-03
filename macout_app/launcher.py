"""Command line entry point shared by ./macout and the built zipapp."""
import os
import sys


def fix_display_for_sudo():
    """sudo often drops X authority. Borrow the invoking user's so the window can open."""
    user = os.environ.get("SUDO_USER")
    if os.geteuid() == 0 and user:
        if not os.environ.get("XAUTHORITY"):
            xa = os.path.join(os.path.expanduser("~" + user), ".Xauthority")
            if os.path.exists(xa):
                os.environ["XAUTHORITY"] = xa
        run = "/run/user/%s" % os.environ.get("SUDO_UID", "")
        if not os.environ.get("WAYLAND_DISPLAY") and os.path.exists(os.path.join(run, "wayland-0")):
            os.environ["XDG_RUNTIME_DIR"] = run
            os.environ["WAYLAND_DISPLAY"] = "wayland-0"


def main():
    args = sys.argv[1:]
    from macout_app import core
    if "--version" in args:
        print("MAC-OUT %s" % core.VERSION)
        return 0
    if "--check" in args:
        env = core.detect_environment()
        print("MAC-OUT %s" % core.VERSION)
        print("Architecture: %s (%s)" % (env["arch"], env["arch_raw"]))
        print("Distribution: %s" % env["distro"])
        for t, p in env["tools"].items():
            print("  %-12s %s" % (t, p or "not found"))
        return 0 if env["tools"]["macchanger"] else 2
    from macout_app import services
    if "--apply-persistent" in args:
        app = services.App()
        for iface, ok in app.persistence.apply_all():
            print("%s: %s" % (iface, "applied" if ok else "FAILED"))
        return 0
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk  # noqa: F401
    except (ImportError, ValueError):
        sys.stderr.write("MAC-OUT needs GTK 3 for Python.\nInstall it with:\n\n  sudo apt install python3-gi gir1.2-gtk-3.0\n")
        return 1
    fix_display_for_sudo()
    from gi.repository import Gdk
    if Gdk.Display.get_default() is None:
        sys.stderr.write("MAC-OUT could not open a display.\nIf you used sudo, try:  sudo -E ./macout\nSee TROUBLESHOOTING.md.\n")
        return 1
    if os.geteuid() != 0:
        sys.stderr.write("Note: not running as root. MAC-OUT will be read-only. Use: sudo ./macout\n")
    app = services.App()
    from macout_app import gui
    gui.main(app)
    return 0
