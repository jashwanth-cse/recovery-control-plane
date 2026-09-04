# Action-Conditional Recovery Model

Phase 8 trains four calibrated binary models that estimate recovery probability
under no intervention, recovery link, payment-method update prompt, and delay. The
models recommend nothing and execute nothing; expected value and next-best-action
selection begin in Phase 9.

## Train

Generate the Phase 7 dataset, then train from the repository root:

```bash
python -m simulator --cases 5000 --seed 42 --output-dir artifacts/simulator
python -m ml --dataset-dir artifacts/simulator --output-dir artifacts/model --seed 42
```

Training writes:

- `model.joblib`: preprocessing and four calibrated estimators
- `metadata.json`: versions, dataset hashes, split sizes, metrics, comparison, and
  model checksum

Only load model artifacts produced by this trusted project. Joblib artifacts are
Python objects and must not be loaded from untrusted sources.

## Feature Boundary

The loader verifies both Phase 7 file hashes and exact schemas before training.
Model inputs exclude case, customer, and payment identifiers and include only:

- amount, attempts, case age, tenure, prior successes/failures, engagement
- currency, failure reason/source, payment method, available methods

Potential outcomes and latent probabilities are read only as supervised labels or
held-out evaluation truth. Automated tests reject any hidden column added to the
visible feature file.

Customers, rather than rows, are split approximately 70/15/15. No customer can
appear in more than one of train, validation, and test.

## Model And Calibration

Each action uses a deterministic scikit-learn pipeline:

```text
numeric passthrough + categorical one-hot encoding
→ gradient-boosted classifier
→ 3-fold sigmoid calibration
```

The metadata records ROC-AUC, PR-AUC, Brier score, log loss, expected calibration
error, and positive rate for validation and test data. The model version is a hash
of model configuration and source dataset hashes.

## Phase 8 Reference Result

For simulator `phase7-v1`, 5,000 cases, dataset seed 42, training seed 42, and 120
boosting stages:

- train: 3,455 rows / 1,102 customers
- validation: 764 rows / 236 customers
- test: 781 rows / 237 customers
- test ROC-AUC: 0.67 to 0.75 across action models
- test expected calibration error: 0.022 to 0.033
- rule-baseline recovery rate: 35.98%
- model-selected recovery rate: 46.22%
- absolute model lift over rules: 10.24 percentage points
- oracle action-selection accuracy: 86.17%

These are reproducible synthetic evaluation results, not claims about production
Razorpay recovery performance.

## Inference

```bash
python -m ml.inference \
  --model artifacts/model/model.joblib \
  --input artifacts/simulator/features.csv \
  --output artifacts/model/predictions.csv
```

Inference validates the visible schema and emits only `case_id` and four action
probabilities. It never reads `ground_truth.csv`.
