# People: gemini-3.5-flash on test-1

Labels: `data/test-1/humans.csv`. 300 frames, one every 1s from the left eye, 25 per request (each request mixes frames from across the clip): 300 answered, 0 failed, 258 scored. Not scored: 28 uncertain, 14 edge.

| Metric | Value |
|---|---|
| Presence recall (frames with people where it said yes) | 0.9787 |
| Presence precision (yes answers that were right) | 0.7541 |
| Presence F1 | 0.8518 |
| False alarm rate (yes on frames with nobody) | 0.1829 |
| TP / FP / FN / TN | 92 / 30 / 2 / 134 |
| Count exact / within 1 (80 frames with people) | 0.7125 / 1.0 |
| Count mean abs error / bias (+ = overcounts) | 0.2875 / 0.1625 |
| Stretches with people where it said yes at least once | 13 of 13 |
| People seen on frames where they were alone in view | 9 of 9 |
| Tokens | promptTokenCount 333276, candidatesTokenCount 13484, thoughtsTokenCount 32018, totalTokenCount 378778 |

## People

`samples` = sampled frames inside the person's span; `alone` = of those, frames where nobody else was in view.

| who | in view | samples | said yes | alone: said yes | flags | description |
|---|---|---|---|---|---|---|
| human1 | 0:00.00–0:03.50 | 4 | 4 | – | intermittent | Seated man, white top, window table |
| human2 | 0:04.00–0:06.00 | 2 | 2 | 1/1 |  | Diner in dark hoodie, front table |
| human3 | 0:04.25–0:06.00 | 1 | 1 | – |  | Diner in cap, same table as human2 |
| human4 | 0:04.25–0:07.00 | 2 | 2 | – |  | Man in light sweater with laptop |
| human5 | 0:04.25–0:07.25 | 3 | 3 | – |  | Woman with curly dark hair, laptop |
| human6 | 0:04.50–0:10.50 | 6 | 6 | – |  | Person in all black, walks to Farmer's Fridge |
| human7 | 0:04.50–0:10.75 | 6 | 6 | – |  | Woman in blue hoodie, eating |
| human8 | 0:04.75–0:10.75 | 6 | 6 | – |  | Dark-haired woman eating with human7 |
| human9 | 0:38.25–0:42.75 | 4 | 4 | – |  | Woman in light jacket |
| human10 | 0:38.25–0:43.00 | 4 | 4 | – |  | Woman in grey jacket, white pants |
| human11 | 0:45.75–0:54.25 | 9 | 9 | – |  | Man with scooter |
| human12 | 0:45.75–0:54.25 | 9 | 9 | – |  | Woman in light top |
| human13 | 0:45.75–0:55.50 | 10 | 10 | – |  | Woman with long dark hair, green jacket |
| human14 | 0:54.00–1:05.75 | 12 | 12 | 10/10 |  | Person in dark clothes |
| human15 | 1:22.25–1:27.75 | 5 | 4 | 3/3 | gap | Person in grey jacket with backpack |
| human16 | 1:30.00–1:35.50 | 6 | 6 | – |  | Man in dark jacket and jeans |
| human17 | 1:30.00–1:35.50 | 6 | 6 | – |  | Man walking with human16 |
| human18 | 1:34.00–1:39.25 | 6 | 5 | 3/4 |  | Runner in pink shirt |
| human19 | 1:46.75–1:51.25 | 5 | 5 | – |  | Woman in dark jacket |
| human20 | 1:46.75–1:51.50 | 5 | 5 | – |  | Woman in white sweatshirt |
| human21 | 1:51.75–1:59.00 | 7 | 7 | 1/1 | gap | Person in dark clothes, left side |
| human22 | 1:52.75–1:58.00 | 5 | 5 | – |  | Woman in white top with backpack |
| human23 | 2:35.50–2:39.00 | 3 | 2 | 2/3 |  | Person in the arcade |
| human24 | 2:58.00–3:03.00 | 5 | 5 | 5/5 |  | Person in grey jacket with backpack |
| human25 | 3:04.50–3:12.50 | 8 | 8 | 8/8 |  | Person in white tee and jeans |
| human26 | 3:48.25–4:09.00 | 20 | 20 | – | intermittent | Man in black shirt carrying a bag |
| human27 | 3:53.50–3:56.25 | 3 | 3 | – |  | Person crossing on the right |
| human28 | 4:32.00–4:40.75 | 9 | 9 | – | approx. appear | Woman in white |
| human29 | 4:32.00–4:40.50 | 9 | 9 | – | approx. appear | Person in dark hoodie |
| human30 | 4:39.25–5:00.00 | 20 | 20 | 13/13 |  | Man in white top, grey beanie, black backpack |
| human31 | 4:41.25–4:42.50 | 1 | 1 | – |  | Scooter rider |
| human32 | 4:44.50–4:49.25 | 5 | 5 | – |  | Person in grey jacket |

## Stretches with someone in view

| from | to | people | samples | said yes |
|---|---|---|---|---|
| 0:00.00 | 0:03.50 | human1 | 4 | 4 |
| 0:04.00 | 0:10.75 | human2, human3, human4, human5, human6, human7, human8 | 7 | 7 |
| 0:38.25 | 0:43.00 | human9, human10 | 4 | 4 |
| 0:45.75 | 1:05.75 | human11, human12, human13, human14 | 20 | 20 |
| 1:22.25 | 1:27.75 | human15 | 5 | 4 |
| 1:30.00 | 1:39.25 | human16, human17, human18 | 10 | 9 |
| 1:46.75 | 1:51.50 | human19, human20 | 5 | 5 |
| 1:51.75 | 1:59.00 | human21, human22 | 7 | 7 |
| 2:35.50 | 2:39.00 | human23 | 3 | 2 |
| 2:58.00 | 3:03.00 | human24 | 5 | 5 |
| 3:04.50 | 3:12.50 | human25 | 8 | 8 |
| 3:48.25 | 4:09.00 | human26, human27 | 20 | 20 |
| 4:32.00 | 5:00.00 | human28, human29, human30, human31, human32 | 28 | 28 |

## Misses (someone in view, model said no)

- 1:36.00 [f00097.jpg](../../frames-left-every30f/f00097.jpg) (labeled 1 in view)
- 2:36.00 [f00157.jpg](../../frames-left-every30f/f00157.jpg) (labeled 1 in view)

## False alarms (nobody labeled, model said yes)

- 0:18.00 [f00019.jpg](../../frames-left-every30f/f00019.jpg): 1 people, "sitting at a table in the background room"
- 0:26.00 [f00027.jpg](../../frames-left-every30f/f00027.jpg): 1 people, "seated at a table in the background on the left"
- 0:27.00 [f00028.jpg](../../frames-left-every30f/f00028.jpg): 1 people, "outside through the glass door on the top left"
- 0:31.00 [f00032.jpg](../../frames-left-every30f/f00032.jpg): 1 people, "on the far left walking under the covered area"
- 1:06.00 [f00067.jpg](../../frames-left-every30f/f00067.jpg): 1 people, "walking beside the camera wearer on the right"
- 1:20.00 [f00081.jpg](../../frames-left-every30f/f00081.jpg): 2 people, "far in the background near street"
- 1:28.00 [f00089.jpg](../../frames-left-every30f/f00089.jpg): 2 people, "walking in the top-center distance and visible at the bottom-right edge"
- 1:40.00 [f00101.jpg](../../frames-left-every30f/f00101.jpg): 2 people, "walking along the path in the top background"
- 1:44.00 [f00105.jpg](../../frames-left-every30f/f00105.jpg): 2 people, "far away on pathway in upper right background"
- 1:45.00 [f00106.jpg](../../frames-left-every30f/f00106.jpg): 2 people, "in the far distance near the road"
- 2:53.00 [f00174.jpg](../../frames-left-every30f/f00174.jpg): 1 people, "far in the distance walking along the walkway"
- 2:54.00 [f00175.jpg](../../frames-left-every30f/f00175.jpg): 1 people, "walking on the path in the distance"
- 2:55.00 [f00176.jpg](../../frames-left-every30f/f00176.jpg): 1 people, "walking down the path in the distance"
- 2:56.00 [f00177.jpg](../../frames-left-every30f/f00177.jpg): 1 people, "far ahead on walkway"
- 2:57.00 [f00178.jpg](../../frames-left-every30f/f00178.jpg): 1 people, "in the distance walking on the pathway"
- 3:04.00 [f00185.jpg](../../frames-left-every30f/f00185.jpg): 2 people, "one walking far down the path and one standing near the building arches on the right"
- 3:15.00 [f00196.jpg](../../frames-left-every30f/f00196.jpg): 2 people, "near the building arches on the right"
- 3:16.00 [f00197.jpg](../../frames-left-every30f/f00197.jpg): 1 people, "near the building arches on the right"
- 3:32.00 [f00213.jpg](../../frames-left-every30f/f00213.jpg): 1 people, "far ahead walking down pathway"
- 3:37.00 [f00218.jpg](../../frames-left-every30f/f00218.jpg): 1 people, "far ahead on the path in the background"
- 3:40.00 [f00221.jpg](../../frames-left-every30f/f00221.jpg): 1 people, "walking away in the far distance on the path"
- 3:42.00 [f00223.jpg](../../frames-left-every30f/f00223.jpg): 1 people, "walking on the path in the far distance"
- 3:43.00 [f00224.jpg](../../frames-left-every30f/f00224.jpg): 1 people, "walking in the distance on the path"
- 3:44.00 [f00225.jpg](../../frames-left-every30f/f00225.jpg): 1 people, "far ahead walking down pathway"
- 3:45.00 [f00226.jpg](../../frames-left-every30f/f00226.jpg): 1 people, "in the distance walking on the pathway"
- 3:46.00 [f00227.jpg](../../frames-left-every30f/f00227.jpg): 1 people, "far down the path"
- 3:47.00 [f00228.jpg](../../frames-left-every30f/f00228.jpg): 1 people, "far ahead in the center of the pathway"
- 4:16.00 [f00257.jpg](../../frames-left-every30f/f00257.jpg): 1 people, "sitting on a bench in the background to the left"
- 4:28.00 [f00269.jpg](../../frames-left-every30f/f00269.jpg): 1 people, "in the distance near the building entrance"
- 4:29.00 [f00270.jpg](../../frames-left-every30f/f00270.jpg): 2 people, "in the distant background near the building archways"
