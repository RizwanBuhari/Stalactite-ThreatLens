# ThreatLens baseline results (2026-10-17 12:47 UTC, s390x / Python 3.12.15)

Model: TF-IDF (word 1-2 + char 3-5 n-grams) + one-vs-rest logistic regression; C=16.0; threshold=0.3 (tuned on val); 397 techniques with >= 3 training examples; fit 103.9 s; 40.3 ms per sentence.

| Split | Subset | Level | Rows | Hit@1 | Hit@3 | Hit@5 | Recall@3 | Micro-F1 | Macro-F1 |
|---|---|---|---|---|---|---|---|---|---|
| val | all | technique | 2883 | 0.605 | 0.803 | 0.859 | 0.783 | 0.581 | 0.358 |
| val | all | parent | 2883 | 0.701 | 0.860 | 0.904 | 0.843 | 0.674 | 0.474 |
| val | clean | technique | 2306 | 0.604 | 0.801 | 0.856 | 0.781 | 0.578 | 0.345 |
| val | clean | parent | 2306 | 0.688 | 0.854 | 0.900 | 0.836 | 0.659 | 0.433 |
| test | all | technique | 3710 | 0.622 | 0.809 | 0.858 | 0.776 | 0.573 | 0.338 |
| test | all | parent | 3710 | 0.707 | 0.866 | 0.906 | 0.838 | 0.658 | 0.475 |
| test | clean | technique | 3028 | 0.616 | 0.797 | 0.851 | 0.759 | 0.559 | 0.320 |
| test | clean | parent | 3028 | 0.688 | 0.853 | 0.897 | 0.821 | 0.633 | 0.426 |
| external_test | all | technique | 2407 | 0.415 | 0.592 | 0.663 | 0.562 | 0.390 | 0.217 |
| external_test | all | parent | 2407 | 0.493 | 0.675 | 0.747 | 0.649 | 0.463 | 0.287 |
| external_test | clean | technique | 2329 | 0.406 | 0.584 | 0.656 | 0.554 | 0.382 | 0.209 |
| external_test | clean | parent | 2329 | 0.483 | 0.668 | 0.742 | 0.641 | 0.453 | 0.276 |

Test split by source (all rows):

| Source | Rows | Hit@3 technique | Hit@3 parent |
|---|---|---|---|
| annoctr | 578 | 0.675 | 0.778 |
| derived_procedure | 515 | 0.592 | 0.670 |
| derived_procedure|expert | 4 | 1.000 | 1.000 |
| derived_procedure|tram | 3 | 1.000 | 1.000 |
| expert | 152 | 0.763 | 0.789 |
| expert|procedure | 1 | 1.000 | 1.000 |
| procedure | 1751 | 0.883 | 0.926 |
| procedure|tram | 6 | 1.000 | 1.000 |
| tram | 700 | 0.899 | 0.943 |
