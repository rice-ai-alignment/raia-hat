printf '\n=== System ===\n'
uname -a
cat /etc/os-release 2>/dev/null
printf '\n=== Board model ===\n'
for f in /proc/device-tree/model /proc/device-tree/compatible; do
  if test -r "$f"; then tr '\000' '\n' < "$f"; fi
done
printf '\n=== Video devices ===\n'
ls -l /dev/video* /dev/media* /dev/v4l-subdev* 2>/dev/null
for f in /sys/class/video4linux/*/name; do
  if test -r "$f"; then printf '%s: ' "$f"; cat "$f"; fi
done
printf '\n=== Processes ===\n'
ps w 2>/dev/null || ps
printf '\n=== Listening services ===\n'
ss -lntup 2>/dev/null || netstat -lntup 2>/dev/null
printf '\n=== Camera tools ===\n'
for tool in v4l2-ctl media-ctl ffmpeg gst-launch-1.0 rkipc rk_mpi_uvc RkLunch.sh RkLunch-stop.sh; do command -v "$tool"; done
printf '\n=== Application directories ===\n'
for d in /oem /oem/usr/bin /userdata /opt /app /usr/bin /etc/init.d; do
  if test -d "$d"; then ls -l "$d" 2>/dev/null | head -100; fi
done
printf '\n=== Camera kernel messages ===\n'
dmesg 2>/dev/null | grep -iE 'camera|sensor|csi|rkcif|rkisp|imx|sc3336|video|ov[0-9]' | tail -100
printf '\n=== Video capabilities ===\n'
if command -v v4l2-ctl >/dev/null 2>&1; then v4l2-ctl --list-devices; fi
printf '\n=== Inspection complete ===\n'
