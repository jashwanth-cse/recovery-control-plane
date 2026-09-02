# Synthetic Data Simulator

Phase 7 provides a deterministic, dependency-free evaluation environment for
revenue-recovery cases. Its distributions and intervention effects are project
engineering assumptions. They do not describe or claim actual Razorpay payment
behavior.

## Generate A Dataset

From the repository root:

```bash
python -m simulator --cases 5000 --seed 42 --output-dir artifacts/simulator
```

The command accepts 1 through 1,000,000 cases and writes:

- `features.csv`: model-visible observed data
- `ground_truth.csv`: evaluation-only counterfactual outcomes
- `manifest.json`: version, configuration, schemas, and SHA-256 checksums

Running the same simulator version with the same seed and case count produces
byte-identical files. A different seed changes generated IDs and data.

## Model-Visible Features

The feature dataset contains stable synthetic case, customer, and payment IDs;
amount and currency; failure reason and source; payment method; attempts and case
age; customer tenure and payment history; engagement score; and available payment
methods.

Customers are reused across cases so history and engagement are internally
consistent. Payment amounts use a bounded long-tail distribution, while failure
profiles, methods, ages, attempts, tenure, and histories vary under the seeded
random generator.

## Hidden Ground Truth

Ground truth contains the potential result for each supported intervention:

```text
would_recover_without_intervention
would_recover_with_recovery_link
would_recover_with_update_prompt
would_recover_after_delay
```

It also contains the simulator's latent probability for each potential outcome.
These columns must never be supplied as model features. `case_id` is the only
column shared between the two files and is used strictly for evaluation joins.

A shared latent outcome draw produces correlated potential outcomes for each case,
allowing later phases to calculate individual counterfactuals without pretending
both outcomes were observed in production.

## Reproducibility Contract

The manifest labels ground truth as `evaluation_only` and records exact field
lists and file hashes. Automated tests enforce:

- byte-identical reruns for equal configuration
- changed output for changed seeds
- exact requested row counts at thousands scale
- visible/hidden schema separation
- varied customer, payment, failure, history, and outcome values
- matching case IDs across observed and hidden files

Phase 7 generates data only. Training, data splits, model serialization, and model
evaluation begin in Phase 8.
