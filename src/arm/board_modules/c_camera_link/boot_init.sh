#!/bin/sh
# LabMate camera autostart v1
set -eu
RUN=/usr/local/lib/labmate-camera/boot.sh
STATE=/tmp/labmate_camera_service
PIDFILE=$STATE/boot.pid

running() {
    pid=$(cat "$PIDFILE" 2>/dev/null || true)
    case "$pid" in ''|*[!0-9]*) return 1 ;; esac
    test -r "/proc/$pid/cmdline" || return 1
    arguments=$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null) || return 1
    case "$arguments" in
        *"$RUN"*) return 0 ;;
        *"c_camera_link.preview_service _run"*"--run-id boot-$pid "*) return 0 ;;
    esac
    return 1
}

case "${1:-start}" in
    start)
        mkdir -p "$STATE"
        if ! mkdir "$STATE/start.lock" 2>/dev/null; then
            echo "Camera start already in progress" >&2
            exit 1
        fi
        trap 'rmdir "$STATE/start.lock"' EXIT
        if running; then echo "Camera already running: $pid"; exit 0; fi
        nohup /bin/sh "$RUN" </dev/null >"$STATE/boot.log" 2>&1 &
        echo "$!" > "$PIDFILE"
        echo "Camera launch requested; status and logs: $STATE"
        ;;
    stop)
        if running; then
            kill -TERM "$pid"
            remaining=12
            while running && test "$remaining" -gt 0; do
                sleep 1
                remaining=$((remaining - 1))
            done
            if running; then echo "Camera stop not confirmed: $pid" >&2; exit 1; fi
        fi
        rm -f "$PIDFILE"
        echo "Camera stopped"
        ;;
    status)
        if running; then
            echo "Camera boot process running: $pid"
            test ! -f "$STATE/status.json" || cat "$STATE/status.json"
        else
            echo "Camera boot process not running"
            test ! -f "$STATE/status.json" || cat "$STATE/status.json"
            exit 3
        fi
        ;;
    restart)
        echo "Stop preview, reset ESP32, then start; SPI token parity may need reset" >&2
        exit 1
        ;;
    *) echo "Usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
