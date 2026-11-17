

| 00:00 | tables;chairs;glass wall;doors;people |
| :---- | :---- |
| 00:10 | people;tables;chairs;wall sign;doors |
| 00:20 | cubby shelves;windows;door;bench |
| 00:30 | bicycle;trash bins;tree;sidewalk;columns;glass door |
| 00:40 | windows;brick wall;sidewalk;people |
| 00:50 | people;wall;columns;sidewalk;grass |
| 01:00 | pedestrian;parked car;tree;columns;sidewalk |
| 01:10 | smartphone;hand;wristwatch;sidewalk;wall;grass |
| 01:20 | sidewalk;columns;tree;street;grass |
| 01:30 | pedestrians;trees;sidewalk;road;drain grate |
| 01:40 | path;trees;road;curb;grass |
| 01:50 | pedestrians;sidewalk;trees;street |
| 02:00 | crosswalk;car;curb;road;sidewalk |
| 02:10 | forked path;trees;grass;arched building |
| 02:20 | large tree;path;grass;building arches |
| 02:30 | trash bins;bicycle racks;columns;grass;path |
| 02:40 | arches;columns;planter;courtyard;brick pavement |
| 02:50 | hand;foot;intersection of paths;grass;tree |
| 03:00 | sidewalk;building arches;young trees;grass |
| 03:10 | pedestrian;smartphone;sidewalk;shrubs;arched building |
| 03:20 | paths;trees;grass;shrubs;arched building |
| 03:30 | sidewalk;trees;building;grass;shadows |
| 03:40 | sidewalk;brick pavers;trees;shrubs;planter |
| 03:50 | distant pedestrian;path;flowerbeds;lamppost;trees |
| 04:00 | distant pedestrian;sidewalk;flowerbeds;grass;building |
| 04:10 | sidewalk;flowerbeds;trees;grass;building |
| 04:20 | sidewalk;shrubs;trees;grass;lamppost |
| 04:30 | path;flowerbeds;distant pedestrian;arched building |
| 04:40 | pedestrians;sidewalk;grass;tree;building;backpack |
| 04:50 | pedestrian;backpack;lamppost;arched building;sidewalk;grass |

Rubric:

**1\. Evaluation rubric**

| Category | Weight | What you're evaluating |
| ----- | ----- | ----- |
| Object identification | 25 | Correctly identifies visible objects such as bicycles, trash bins, cars, and phones |
| Person detection and counting | 15 | Detects people and counts them without duplication |
| Spatial reasoning | 20 | Identifies object locations and spatial relationships |
| Temporal reasoning | 15 | Understands when objects appear, disappear, or move |
| Distance estimation | 15 | Estimates relative distances and, when calibrated ground truth exists, metric distances |
| Uncertainty and hallucination | 10 | Avoids inventing information not supported by the footage |
| **Total** | **100** |  |

**Eval 1 — Object identification**

10 points

Timestamp: 00:30

**Question:** What type of vehicle or personal transportation device appears near the right edge of the frame?

**Ground truth:** Bicycle.

**Eval 2 — Person detection**

10 points

Timestamp: 01:50

**Question:** How many clearly visible pedestrians are approaching on the path?

**Ground truth:** Two, with a possible additional person behind them.

**Eval 3 — Spatial reasoning**

10 points

Timestamp: 01:00

**Question:** On which side of the camera's view is the parked vehicle?

**Ground truth:** Right side.

**Eval 4 — Temporal reasoning**

10 points

Timestamp: 01:00–01:10

**Question:** What handheld electronic device becomes visible in this interval?

**Ground truth:** Smartphone.

**Eval 5 — Grounded spatial description**

10 points

Timestamp: 02:30

**Question:** What objects are visible near the building along the path?

**Ground truth:** Two dark trash bins and multiple bicycle racks.

