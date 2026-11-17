# Rubric: gemini-3.5-flash on test-1

Model under test `gemini-3.5-flash`, judge `gemini-3.1-flash-lite`, left eye. Rubric `data/test-1/rubric.md`.

Person and hallucination evidence from `eval/out/test-1/people/gemini-3.5-flash-left-every30f-batch25`.

## Scorecard

**79.0 of 85 points** on the categories with evidence (85 of 100 weight covered; 93% of covered).

| Category | Weight | Score (0–1) | Points | Evidence |
|---|---|---|---|---|
| Object identification | 25 | 0.92 | 23.0 | object recall over 30 timestamps = 0.84; Eval 1: Object identification = 1.00 |
| Person detection and counting | 15 | 0.85 | 12.8 | people eval: presence F1 = 0.85; people eval: exact count rate = 0.71; Eval 2: Person detection = 1.00 |
| Spatial reasoning | 20 | 1.00 | 20.0 | Eval 3: Spatial reasoning = 1.00; Eval 5: Grounded spatial description = 1.00 |
| Temporal reasoning | 15 | 1.00 | 15.0 | Eval 4: Temporal reasoning = 1.00 |
| Distance estimation | 15 | not covered | – | no evals yet |
| Uncertainty and hallucination | 10 | 0.82 | 8.2 | people eval: 1 − false alarm rate = 0.82 |

Each category is the plain mean of its evidence. Object recall can't penalize extra objects, because the annotations list only the main things in each frame.

## Question checks

| Eval | Time | Question | Ground truth | Model's answer | Points | Judge |
|---|---|---|---|---|---|---|
| 1 Object identification | 00:30 | What type of vehicle or personal transportation device appears near the right edge of the frame? | Bicycle. | bicycle | 10 / 10 | correct: The model correctly identified the vehicle as a bicycle. |
| 2 Person detection | 01:50 | How many clearly visible pedestrians are approaching on the path? | Two, with a possible additional person behind them. | 2 | 10 / 10 | correct: The model identified the two primary pedestrians which matches the core of the ground truth. |
| 3 Spatial reasoning | 01:00 | On which side of the camera's view is the parked vehicle? | Right side. | on the right side | 10 / 10 | correct: The model correctly identified the position of the vehicle as the right side. |
| 4 Temporal reasoning | 01:00–01:10 | What handheld electronic device becomes visible in this interval? | Smartphone. | smartphone | 10 / 10 | correct: The model correctly identified the smartphone. |
| 5 Grounded spatial description | 02:30 | What objects are visible near the building along the path? | Two dark trash bins and multiple bicycle racks. | bike racks, trash cans, and a recycling bin | 10 / 10 | correct: The model identified the trash containers and bike racks mentioned in the ground truth. |

## Objects

Found / annotated per timestamp; missing items in bold. Frames: `eval/out/test-1/frames-left-rubric`.

| Time | Found | Annotated objects | Model listed |
|---|---|---|---|
| 00:00 | 4/5 | tables, chairs, glass wall, **doors**, people | phone, table, chair, glass wall, glass partition, floor, person |
| 00:10 | 3/5 | people, tables, chairs, **wall sign**, **doors** | vending machine, table, chair, person, glass wall, floor, wall |
| 00:20 | 3/4 | cubby shelves, **windows**, door, bench | shelving unit, bench, glass door, exit sign, floor, wall |
| 00:30 | 6/6 | bicycle, trash bins, tree, sidewalk, columns, glass door | trash bin, glass door, pillar, bicycle, walkway, tree, light fixture |
| 00:40 | 3/4 | windows, **brick wall**, sidewalk, people | wooden wall, window, blinds, walkway, person |
| 00:50 | 5/5 | people, wall, columns, sidewalk, grass | wooden wall, pillar, walkway, grass, person, car |
| 01:00 | 5/5 | pedestrian, parked car, tree, columns, sidewalk | wooden wall, pillar, walkway, grass, person, car, tree |
| 01:10 | 6/6 | smartphone, hand, wristwatch, sidewalk, wall, grass | phone, hand, arm, wristband, foot, walkway, wooden wall, grass |
| 01:20 | 5/5 | sidewalk, columns, tree, street, grass | wooden wall, pillar, walkway, grass, tree, road, car |
| 01:30 | 5/5 | pedestrians, trees, sidewalk, road, drain grate | walkway, grass, tree, drain cover, person, road, car, lamp post |
| 01:40 | 4/5 | path, trees, road, **curb**, grass | walkway, metal grate, grass, tree, road, hand |
| 01:50 | 4/4 | pedestrians, sidewalk, trees, street | walkway, person, tree, grass, road, lamp post |
| 02:00 | 4/5 | crosswalk, car, **curb**, road, sidewalk | crosswalk, road, car, sidewalk, hand, foot |
| 02:10 | 4/4 | forked path, trees, grass, arched building | walkway, grass, tree, building |
| 02:20 | 4/4 | large tree, path, grass, building arches | walkway, grass, tree, building, trash bin |
| 02:30 | 5/5 | trash bins, bicycle racks, columns, grass, path | sidewalk, grass, trash bin, bike rack, building, pillar, hand, foot |
| 02:40 | 2/5 | **arches**, columns, **planter**, **courtyard**, brick pavement | sidewalk, building, pillar, grass, tree, sky |
| 02:50 | 4/5 | hand, foot, **intersection of paths**, grass, tree | sidewalk, grass, tree, lamp post, building, hand, foot |
| 03:00 | 4/4 | sidewalk, building arches, young trees, grass | sidewalk, grass, tree, lamp post, building, person |
| 03:10 | 4/5 | pedestrian, smartphone, sidewalk, **shrubs**, arched building | sidewalk, grass, tree, lamp post, building, person, hand, smartphone |
| 03:20 | 4/5 | paths, trees, grass, **shrubs**, arched building | sidewalk, grass, tree, building |
| 03:30 | 4/5 | sidewalk, trees, building, grass, **shadows** | sidewalk, grass, tree, lamp post, building |
| 03:40 | 2/5 | sidewalk, **brick pavers**, trees, **shrubs**, **planter** | sidewalk, flowers, tree, trash bin, bench |
| 03:50 | 5/5 | distant pedestrian, path, flowerbeds, lamppost, trees | sidewalk, flowers, plants, tree, lamp post, person, hand |
| 04:00 | 4/5 | distant pedestrian, sidewalk, flowerbeds, **grass**, building | sidewalk, flowers, plants, tree, lamp post, building, person |
| 04:10 | 5/5 | sidewalk, flowerbeds, trees, grass, building | sidewalk, flowers, plants, tree, grass, building |
| 04:20 | 2/5 | sidewalk, **shrubs**, trees, **grass**, **lamppost** | sidewalk, plants, tree, building, bench |
| 04:30 | 3/4 | path, **flowerbeds**, distant pedestrian, arched building | sidewalk, plants, tree, building, person |
| 04:40 | 4/6 | pedestrians, sidewalk, grass, **tree**, building, **backpack** | sidewalk, grass, building, person, hand, smartphone |
| 04:50 | 6/6 | pedestrian, backpack, lamppost, arched building, sidewalk, grass | sidewalk, grass, building, person, backpack, lamp post, tree |

Tokens, model under test: promptTokenCount 50349, candidatesTokenCount 1786, thoughtsTokenCount 3183, totalTokenCount 55318. Judge: promptTokenCount 3670, candidatesTokenCount 4491, thoughtsTokenCount 0, totalTokenCount 8161.
