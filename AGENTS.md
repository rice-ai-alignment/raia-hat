# Instructions for coding agents

This repo controls the RAIA Labs recording hat, a LubanCat RK3566 board with a stereo camera and an IMU. You reach it from a Mac over USB. **Use `./hat` for everything.** Every subcommand is non-interactive except `./hat ssh` with no arguments. Do not edit `lib/` or `rndis-mac/` to get a normal download working.

## Standard flow: "download my footage"

```sh
./hat status                 # is the bridge up? is the hat recording?
./hat password <PW>          # only if a command says the password isn't set (ask the user for it)
./hat setup                  # only if status/connect says the bridge isn't built
./hat connect                # only if bridge is "not running"
./hat list                   # sessions on the hat
./hat download               # newest session  (or: ./hat download <SESSION> / --all)
```

When a download succeeds, the last line printed is `DOWNLOADED <path>`. Report that path to the user.

## Things that need the human

- **Plugging in.** If `connect` prints `Hat not found on USB`, ask the user to power on the hat and plug it in with a USB *data* cable, then retry.
- **Mac admin password.** `./hat connect` needs root to create a network interface. If it can't use `sudo` without a password, it opens a macOS password dialog. Tell the user to watch for the dialog. If they cancel it or no GUI is available, ask them to run `./hat connect` in their own terminal. In Claude Code they can type `! ./hat connect`. Once the bridge is running, unplugging and replugging the hat reconnects on its own, so don't run `connect` again (and trigger another password dialog) unless `./hat status` says the bridge is not running.
- **Stopping a recording.** If download prints `STILL_RECORDING`, the user has to flip the physical switch on the hat. You cannot stop a recording remotely, and you must not kill the recorder process.

## Rules

- **Never delete footage unless the user asks.** `./hat delete <SESSION>` refuses unless `captures/<SESSION>/manifest.json` exists and every file matches its recorded size. Do not get around this check with raw `rm` over SSH.
- Do not stop, restart, or reconfigure `video-recorder.service` or anything in `/opt/device_scripts` on the hat.
- Credentials: the user is `cat`. The password is **not** in this repo. If a command prints `Hat password not set`, ask the user for it, then run `./hat password '<password>'`. That saves it to `.hat/password`, which git ignores. Never write the password into any tracked file, commit, or message.
- The hat's clock is wrong. Do not infer real recording dates from session names; use the order of the sessions instead.
- `.hat/` contains runtime state: `bridge.log`, `bridge.pid`, `network.json`, and `known_hosts`. Read `.hat/bridge.log` first when debugging the link. `bridge.log` and `bridge.pid` are links to root-owned files in `/var/run/raia-hat/`, where root runs its own copy of the bridge. Keep it that way: root must never execute or write a file the user account can modify.
- The hat's SSH server drops some new connections (`kex_exchange_identification: read: Connection reset by peer`). Retry the command a few times before treating the link as broken.

## Useful facts

- Over USB, the hat is `192.168.77.2` and the Mac is `192.168.77.1`.
- Recordings live in `/data/` on the hat, owned by root. Each session has `<id>_<YYYYMMDD>_<HHMMSS>_NNNNN.mp4` (5-minute segments), `<session>.bin` (IMU), and `<session>.txt2` (timestamps).
- Video is 3840×1080 side-by-side stereo HEVC at 30 fps. Left eye is `crop=1920:1080:0:0` and right eye is `crop=1920:1080:1920:0`.
- Run root commands on the hat with `./hat sudo '<cmd>'`. Other useful checks: `/opt/device_scripts/lsrecord.sh` prints 1 while recording, and `df -h /data` shows free space.

## Evals (`eval/`)

These score a vision-language model on hat footage against hand-written ground truth. See the README section "Evaluating vision models on the footage" and the reports in `eval/reports/`.

- Clips are registered in `eval/clips.json`. Each clip's files are in `data/<clip>/`: the video (git-ignored), `humans.csv` (people ground truth), and `rubric.md` (objects, question checks, category weights).
- `data/<clip>/humans.csv` and `rubric.md` are the user's ground truth. Don't edit them unless the user asks. Propose label fixes in a separate file instead.
- Run `python3 eval/vlm_eval.py <clip>` for people and `python3 eval/rubric_eval.py <clip>` for the rubric. After editing labels, re-score with `--score-only` (people) or rerun the rubric eval; both reuse cached answers in `eval/out/` and make no new model calls.
- The Gemini key is `GEMINI_KEY` in `.env.local` (git-ignored, mode 600). Never print it or commit it.
- The key is on the free tier: 20 requests per model per day, and no quota at all for the Pro models. The scripts batch frames to fit and stop cleanly when a daily quota runs out. Rerun the same command after the reset (midnight Pacific) to continue. Ask before switching to a setup that costs money.
