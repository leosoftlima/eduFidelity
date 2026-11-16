# Real pages: first run

> Six pages of **one module of an existing course** built with the generation platform, measured locally against their design frames. **They are not outputs of the study's experimental conditions, and these are not study results.** The pages, screenshots and texts are not in this repository; only these numbers are. Matching parameters are the provisional defaults; the pairs have not been verified yet.

The design frames draw the learning platform around the course content (header, navigation, side panel). Following the authors' decision of 16/11/2026, the reference is the **content area** only: the same region of every frame of the course (x 42, y 108, width 1400 px, to the bottom of the frame), declared before measuring and recorded in each reference (`content_region`). The generated pages are rendered at the region's width.

| Page | Reference elements | Generated elements | Matched | EP F1 | Layout Fidelity | SSIM |
|---|---:|---:|---:|---:|---:|---:|
| A-m1-p1 | 27 | 34 | 17 | 0.557 | 0.158 | 0.794 |
| A-m1-p2 | 114 | 23 | 13 | 0.190 | 0.110 | 0.680 |
| A-m1-p3 | 25 | 21 | 11 | 0.478 | 0.028 | 0.764 |
| A-m1-p4 | 45 | 49 | 31 | 0.660 | 0.318 | 0.765 |
| A-m1-p5 | 44 | 71 | 37 | 0.643 | 0.030 | 0.816 |
| A-m1-p6 | 43 | 70 | 39 | 0.690 | 0.096 | 0.829 |

Before cropping, with the platform in the reference, Layout Fidelity was 0.03 to 0.15 and Element Preservation F1 0.19 to 0.62. Cropping raised F1 on five of the six pages; the sixth stayed at 0.19.

## What the first run shows

1. **Layout Fidelity stays low (0.03 to 0.32) for a reason that is not the platform.** Matched elements sit about 20 px apart at the top of the page and 60 to 260 px apart at the bottom (1% to 5% of the page height): the generated page drifts a little at every block. Text lines are thin boxes, so any vertical drift drives their IoU to zero. This is open question Q1 measured on real pages: as defined, mean IoU punishes accumulated drift as if the layout were lost.
2. **Element counts differ a lot on some pages** (one page has 114 reference elements and 23 generated). Whether that is a real loss or a difference in how each side splits content into elements is what the pair verification has to tell.
3. The pairs proposed by the matcher are ready for verification on the review pages; once verified, they feed `tune-matching` and `freeze-matching` (M4). The pages used here must stay out of the study's page selection.
