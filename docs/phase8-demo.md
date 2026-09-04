# Phase 8 Demonstration

This is a five-minute recording flow for the ML Recoverability / Action Model.
All reported recovery results are synthetic simulator results, not production claims.

## 1. Show the running control plane

```powershell
docker compose up --detach api web
Invoke-RestMethod http://localhost:8000/health/ready | ConvertTo-Json -Depth 4
```

Open:

- Web application: http://localhost:3000
- Interactive API documentation: http://localhost:8000/docs

Say: "The control plane is running with healthy PostgreSQL and Redis dependencies.
The API version is 0.9.0-phase8. Earlier phases ingest payment signals, create
recovery cases, calculate revenue at risk, and provide a deterministic rule baseline."

## 2. Explain the leakage boundary

```powershell
Get-Content artifacts/simulator-phase7/features.csv -TotalCount 2
Get-Content artifacts/simulator-phase7/ground_truth.csv -TotalCount 2
Get-Content artifacts/simulator-phase7/manifest.json
```

Say: "The simulator writes model-visible features and hidden counterfactual truth
to separate checksum-protected files. Training features exclude case, customer, and
payment identifiers. Hidden probabilities are used only to create labels and evaluate
action selection, never as model inputs."

## 3. Train the four action-conditional models

```powershell
python -m ml --dataset-dir artifacts/simulator-phase7 --output-dir artifacts/demo-phase8 --seed 42 --max-iter 120
```

Say: "The pipeline validates the manifest and schemas, splits by customer to prevent
cross-split leakage, and trains one calibrated gradient-boosted binary model for each
candidate action: no intervention, recovery link, update prompt, and delay. The model
version is reproducibly bound to the dataset hashes and training configuration."

## 4. Show held-out evaluation

```powershell
$m = Get-Content artifacts/demo-phase8/metadata.json | ConvertFrom-Json
$m.model_version
$m.splits | ConvertTo-Json -Depth 3
$m.rule_baseline_comparison | Format-List
$m.metrics.test | ConvertTo-Json -Depth 3
```

Say: "On the fixed 5,000-case synthetic evaluation, the deterministic rule baseline
recovered 35.98 percent and model-selected actions recovered 46.22 percent, an absolute
lift of 10.24 percentage points. Test ROC-AUC ranges from 0.6708 to 0.7454 and expected
calibration error ranges from 0.0224 to 0.0331. These are synthetic validation metrics."

## 5. Run inference and prove the output boundary

```powershell
python -m ml.inference --model artifacts/demo-phase8/model.joblib --input artifacts/simulator-phase7/features.csv --output artifacts/demo-phase8/predictions.csv
Get-Content artifacts/demo-phase8/predictions.csv -TotalCount 3
```

Say: "Inference accepts only the visible feature schema and returns a case ID plus four
action-conditional probabilities. It does not expose hidden outcomes. Phase 8 recommends
probabilities only; deterministic policy gating and provider execution remain separate."

## 6. Close with acceptance evidence

```powershell
python -m pytest -q
```

Say: "All 66 tests pass, including split isolation, hidden-column rejection, probability
bounds, calibration metrics, artifact checksum and reload, and inference schema tests.
Phase 8 is complete. Phase 9 will convert these probabilities into expected-value-ranked
next-best actions, so that behavior is intentionally not included here."
