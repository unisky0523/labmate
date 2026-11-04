#!/bin/sh
# Read-only inspection. Run on the board; does not modify boot media.
uname -a
printf '\nSPI devices\n'
ls -l /sys/bus/spi/devices /dev/spidev* 2>/dev/null
printf '\nPS GPIO controller\n'
for g in /sys/class/gpio/gpiochip*; do
    test -d "$g" || continue
    printf '%s label=' "$g"; cat "$g/label"
    printf 'base='; cat "$g/base"
done
printf '\nVideo devices\n'
ls -l /dev/video* 2>/dev/null
printf '\nSPI kernel messages\n'
dmesg | grep -i spi | tail -n 20
