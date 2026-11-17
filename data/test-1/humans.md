# Human appearances: test-1

`humans.csv` lists every person who enters and leaves the frame in `test-1.mp4` (5:00 long, 30 fps, 3840x1080 side-by-side stereo). `test-1.mp4` is hat file `19166522959_20260907_121843_00005.mp4` (session `19166522959_20260907_121843`, segment 5), referred to below as segment_00005.

## Columns

| Column | Meaning |
|---|---|
| `label` | `human1` to `human32`, numbered by first appearance |
| `description` | Short visual description for telling people apart |
| `scene` | Where the camera is: cafeteria, covered walkway, path, arcade |
| `appears_s` / `leaves_s` | Times in seconds from video start |
| `appears_ts` / `leaves_ts` | Same times as `m:ss.ss` |
| `end_reason` | How the person left: `passes camera`, `exits frame`, `occluded`, or `video ends` |
| `notes` | Gaps, groupings, and uncertainty |

## Definitions

- **Appears:** the first frame where the person is visible, often as a small figure far away.
- **Leaves:** the first frame where the person is gone, because they walked out of frame or went behind something.
- **One person, one row:** if someone drops out briefly (camera tilt, a pillar) and comes back, they keep one label. The `notes` column flags these gaps.

## Method

1. Ran a YOLOv8s person detector with ByteTrack on the left camera view at 4 frames per second.
2. Removed detections of the camera wearer's own hands, legs, and phone.
3. Linked detections into tracks, then checked every track by eye at quarter-second steps to confirm identities, merge broken tracks, and fix enter and exit times.

## Accuracy and limits

- **Timing:** about ±0.25 seconds.
- **Cafeteria (0:00 to 0:11):** least certain. The camera tilts down toward the phone often, so seated diners flicker in and out. Each diner gets one first and last sighting.
- **Distant figures:** appear times for far-off people (human26, human28, human29) are approximate.
- **Excluded:** the camera wearer; a few specks too small to tell apart (around 1:25 and 3:08); the right half of the frame, a near duplicate of the left view.
