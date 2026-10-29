# Shiftnote evaluation: mock (rules-v1)

8 synthetic handover notes in English, German and Indonesian.

| Metric | Result |
|---|---|
| Vitals precision / recall | 100% / 93% |
| Medications found | 0% |
| Medication status correct (given / refused / held) | – |
| Next-shift tasks found | 36% |
| Risk flags precision / recall | – / 0% |
| Ambiguous dose flagged, not guessed | 100% |
| Invented or invalid items caught by checks | 0 |
| Fell back to rules | 0% |
| Passed every check first time or after repair | 0% |
| Mean attempts per note | 1.00 |
| Latency p50 / p95 | 0 ms / 8 ms |

## Per case

| Case | Status | Vitals | Meds | Tasks | Risks | Notes |
|---|---|---|---|---|---|---|
| de-fever-infection | needs_review | 4/4 | 0/1 | 0/2 | 0/2 | missed medication paracetamol; missed task 'temperature'; missed task 'urine'; missed risk deterioration; missed risk infection |
| de-nursing-home-diabetes | needs_review | 4/4 | 0/1 | 0/1 | 0/2 | missed medication insulin; missed task 'glucose' by 11:30; missed risk fall; missed risk allergy |
| en-ambiguous-dose | needs_review | 2/3 | 0/1 | 1/1 | 0/0 | missed vital pain_score 3; missed medication morphine |
| en-no-vitals-social | needs_review | 0/0 | 0/0 | 0/1 | 0/0 | missed task 'doctor' by 14:00 |
| en-postop-hip | needs_review | 5/5 | 0/1 | 1/2 | 0/2 | missed medication paracetamol; missed task 'dressing'; missed risk fall; missed risk pressure_injury |
| en-refused-and-held | needs_review | 3/4 | 0/2 | 1/1 | 0/0 | missed vital blood_glucose 6.1; missed medication metoprolol; missed medication insulin |
| id-ward-hypotension | needs_review | 4/4 | 0/1 | 0/1 | 0/1 | missed medication ceftriaxone; missed task 'blood pressure' by 10:00; missed risk deterioration |
| mixed-id-en-fall | needs_review | 3/3 | 0/0 | 1/2 | 0/1 | missed task 'bell'; missed risk fall |
