# RAIA Labs Recording Hat

Record egocentric stereo video and IMU data with the hat, then copy it to your Mac with one command.

```sh
git clone <this repo> raia-hat && cd raia-hat
./hat setup        # one time: installs libusb + Rust via Homebrew, builds the USB bridge
./hat password     # one time: paste the hat password (ask the RAIA team; it is not in this repo)
# plug the hat into the Mac with a USB data cable
./hat connect      # asks for your Mac password once
./hat download     # newest stopped recording → ./captures/<session>/
```

**Using a coding agent (Claude Code, Codex, Cursor, …)?** Open this folder in the agent and ask it to "download my hat footage". `AGENTS.md` tells it what to do.

---

## The hat

| | |
|---|---|
| Computer | Embedfire LubanCat board (Rockchip RK3566), running Debian |
| Camera | Stereo. Each frame is **3840×1080** with the left and right eyes **side by side** (1920×1080 each), at **30 fps**, encoded as **HEVC/H.265** at about 8 Mbps |
| IMU | ICM-42688-P, with one `.bin` file per session |
| Storage | SD card, at `/data` on the hat. Recordings stay there until you delete them |
| Login | `ssh cat@192.168.77.2`. Ask the RAIA team for the password (it is also the `sudo` password). `./hat password` saves it to `.hat/password`, which git ignores |

## Recording

1. **Power on** the hat and let it boot. On startup it checks the camera and the IMU.
2. **Flip the switch** to start recording. The LED blinks while it records, and Wi-Fi is turned off during recording.
3. **Flip the switch back** to stop. Wait a few seconds for the files to finish saving.

Tips:
- Move slowly. Fast head turns cause motion blur.
- Use good light.
- To capture a space, walk around it, and look at the floor, the ceiling, and the corners.
- The hat **stops recording on its own when free space drops below 2 GB.** Run `./hat status` to see free space.

## Commands

| Command | What it does |
|---|---|
| `./hat password [PW]` | Saves the hat password locally. Run it once. |
| `./hat setup` | Installs the dependencies and builds the USB bridge. Run it once. |
| `./hat connect` | Starts the USB network link in the background. The hat appears at `192.168.77.2`. |
| `./hat status` | Shows whether the link is up, whether the hat is recording, and how much space is free |
| `./hat list` | Lists the recording sessions on the hat |
| `./hat download [SESSION]` | Copies a session and checks every file by SHA-256. The default is the newest session. |
| `./hat download --all` | Downloads every stopped session that isn't already downloaded |
| `./hat delete SESSION` | Frees space on the hat. It refuses unless a verified local copy exists. |
| `./hat ssh [CMD]` | Opens a shell on the hat, or runs `CMD` there |
| `./hat sudo CMD` | Runs `CMD` on the hat as root (for example, `./hat sudo 'ls -lh /data'`) |
| `./hat disconnect` | Stops the USB link |

## What you get

```
captures/<session>/              e.g. 19166522959_20260907_122746
  segment_00000.mp4              stereo video, cut into 5-minute segments with no dropped frames
  segment_00001.mp4 …
  imu.bin                        IMU data for the whole session
  frame-timestamps.txt           per-frame timestamps
  manifest.json                  original names, sizes, SHA-256 hashes, video info (written last = download complete)
```

Session names follow the pattern `<deviceID>_<YYYYMMDD>_<HHMMSS>`. ⚠️ **The hat's clock is wrong** (one Nov 2026 session was stamped Sept 2026), so don't rely on the date in the name.

Split the video into left and right eyes:
```sh
ffmpeg -i segment_00000.mp4 -vf "crop=1920:1080:0:0"    left.mp4
ffmpeg -i segment_00000.mp4 -vf "crop=1920:1080:1920:0" right.mp4
```
The stereo pair **isn't calibrated yet**: the lens intrinsics and the distance between the cameras are unknown. The format of the IMU `.bin` file isn't documented yet.

## How the connection works

The hat's USB port acts as a network adapter of a type called RNDIS. macOS has no RNDIS driver anymore, so `rndis-mac/` contains a userspace bridge. It is a patched copy of [Zorglub51/rndis-mac](https://github.com/Zorglub51/rndis-mac) (MIT); `rndis-mac/HAT_PATCH.diff` shows the changes. The patch adds a small DHCP responder that gives the hat the IP address `192.168.77.2`. The Mac uses `192.168.77.1`. The bridge needs administrator rights only to create its network interface.

Runtime state, such as the bridge PID, logs, and the hat's SSH host key, is stored in `.hat/`, which git ignores.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Hat not found on USB` | Make sure the hat is on, then replug it. Use a **data** cable, not a charge-only one. |
| `Bridge is up but the hat's SSH isn't answering` | Wait about 10 seconds and run `./hat status`. If it still fails, run `./hat disconnect && ./hat connect`. |
| `STILL_RECORDING` | Flip the switch to stop, wait a few seconds, and retry. |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | You're using a different hat, or the hat was re-flashed. Run `rm .hat/known_hosts`. |
| A copy drops partway through | The script retries 6 times. If it still fails, run `./hat disconnect && ./hat connect` and download again. Downloads that already finished are skipped. |
| Green bands at the bottom of frames | A known camera firmware glitch. The recorder resets the camera before each session; stop and start the recording again. |
| Recording stopped by itself | There's less than 2 GB free. Download, then use `./hat delete`. |

Only macOS has been tested. Linux and Windows have native RNDIS drivers but need a DHCP server on the USB interface that gives the hat `192.168.77.2`.
