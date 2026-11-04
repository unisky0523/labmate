#!/bin/sh
# Run an isolated screen test and restore the vendor desktop on exit.
cd /home/root/labmate_ui_test || exit 1
test -x ./labassistant || { echo 'labassistant missing or not executable'; exit 1; }
factory_pids=
# The factory desktop owns this child and restores itself when it exits.
# A serial launch retains the existing stop/restore behavior.
if [ "${LABMATE_DESKTOP_CHILD:-0}" != 1 ]; then
    factory_pids=$(pidof QMainApp 2>/dev/null)
fi
restore=0
restore_desktop() {
    if [ "$restore" = 1 ]; then
        /etc/init.d/qtGUI.sh start
        echo 'Vendor desktop restarted.'
    fi
}
trap restore_desktop EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ -n "$factory_pids" ]; then
    kill $factory_pids || exit 1
    restore=1
    count=0
    while pidof QMainApp >/dev/null 2>&1; do
        count=$((count + 1))
        if [ "$count" -ge 5 ]; then
            restore=0
            echo 'Vendor desktop did not exit. Test not started.'
            exit 1
        fi
        sleep 1
    done
fi
export QT_QPA_PLATFORM=linuxfb:fb=/dev/fb0
export QT_QPA_FONTDIR=/usr/share/fonts
export TSLIB_TSDEVICE=/dev/input/by-path/platform-e0005000.i2c-event
export TSLIB_CONSOLEDEVICE=none
export TSLIB_FBDEVICE=/dev/fb0
export TSLIB_CONFFILE=/etc/ts.conf
export TSLIB_PLUGINDIR=/usr/lib/ts
echo 'Opening LabMate UI. Close the assistant on the screen to finish.'
./labassistant >run.log 2>&1
result=$?
echo "Assistant exit code: $result"
if [ "$result" -ne 0 ]; then
    tail -n 40 run.log
fi
exit "$result"
