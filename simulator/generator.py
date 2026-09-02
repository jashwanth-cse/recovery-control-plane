import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

SIMULATOR_VERSION = "phase7-v1"

VISIBLE_FIELDS = (
    "case_id",
    "customer_id",
    "payment_id",
    "amount",
    "currency",
    "failure_reason",
    "failure_source",
    "payment_method",
    "attempt_count",
    "case_age_days",
    "customer_tenure_days",
    "prior_successes",
    "prior_failures",
    "engagement_score",
    "available_methods",
)

HIDDEN_FIELDS = (
    "case_id",
    "would_recover_without_intervention",
    "would_recover_with_recovery_link",
    "would_recover_with_update_prompt",
    "would_recover_after_delay",
    "p_without_intervention",
    "p_recovery_link",
    "p_update_prompt",
    "p_delay",
)

PAYMENT_METHODS = ("card", "upi", "netbanking", "wallet")


@dataclass(frozen=True)
class FailureProfile:
    reason: str
    source: str
    weight: int
    base_adjustment: float
    link_lift: float
    update_lift: float
    delay_lift: float


FAILURE_PROFILES = (
    FailureProfile("payment_timed_out", "gateway", 18, 0.08, 0.24, 0.05, 0.18),
    FailureProfile("bank_error", "bank", 20, 0.03, 0.22, 0.04, 0.15),
    FailureProfile("insufficient_funds", "customer", 22, -0.18, 0.05, 0.08, 0.20),
    FailureProfile("authentication_failed", "customer", 16, -0.07, 0.10, 0.20, 0.03),
    FailureProfile("payment_cancelled", "customer", 12, -0.12, 0.08, 0.11, 0.04),
    FailureProfile("issuer_declined", "bank", 12, -0.15, 0.10, 0.15, 0.07),
)


@dataclass(frozen=True)
class SimulationConfig:
    case_count: int = 5000
    seed: int = 42

    def validate(self) -> None:
        if self.case_count < 1 or self.case_count > 1_000_000:
            raise ValueError("case_count must be between 1 and 1,000,000")


@dataclass(frozen=True)
class CustomerProfile:
    customer_id: str
    tenure_days: int
    prior_successes: int
    prior_failures: int
    engagement_score: float
    available_methods: tuple[str, ...]


class SyntheticDatasetGenerator:
    def __init__(self, config: SimulationConfig) -> None:
        config.validate()
        self.config = config
        self.random = random.Random(config.seed)

    def generate(self, output_dir: Path) -> dict[str, Any]:
        self.random = random.Random(self.config.seed)
        output_dir.mkdir(parents=True, exist_ok=True)
        visible_path = output_dir / "features.csv"
        hidden_path = output_dir / "ground_truth.csv"
        customer_count = max(1, math.ceil(self.config.case_count / 3))
        customers = [self._customer(index) for index in range(customer_count)]

        with self._atomic_csv(visible_path, VISIBLE_FIELDS) as visible_writer, self._atomic_csv(
            hidden_path, HIDDEN_FIELDS
        ) as hidden_writer:
            for index in range(self.config.case_count):
                customer = customers[self.random.randrange(customer_count)]
                visible, hidden = self._case(index, customer)
                visible_writer.writerow(visible)
                hidden_writer.writerow(hidden)

        manifest = {
            "simulator_version": SIMULATOR_VERSION,
            "seed": self.config.seed,
            "case_count": self.config.case_count,
            "customer_count": customer_count,
            "features": {
                "file": visible_path.name,
                "fields": list(VISIBLE_FIELDS),
                "sha256": self._sha256(visible_path),
            },
            "ground_truth": {
                "file": hidden_path.name,
                "fields": list(HIDDEN_FIELDS),
                "sha256": self._sha256(hidden_path),
                "access": "evaluation_only",
            },
        }
        self._atomic_json(output_dir / "manifest.json", manifest)
        return manifest

    def _customer(self, index: int) -> CustomerProfile:
        tenure_days = self.random.randint(7, 3650)
        history_size = self.random.randint(0, min(80, max(2, tenure_days // 20)))
        engagement = round(self.random.betavariate(2.2, 2.0), 4)
        success_rate = 0.35 + engagement * 0.55
        prior_successes = sum(
            self.random.random() < success_rate for _ in range(history_size)
        )
        available_count = self.random.randint(1, len(PAYMENT_METHODS))
        available_methods = tuple(
            sorted(self.random.sample(PAYMENT_METHODS, available_count))
        )
        return CustomerProfile(
            customer_id=self._id("customer", index),
            tenure_days=tenure_days,
            prior_successes=prior_successes,
            prior_failures=history_size - prior_successes,
            engagement_score=engagement,
            available_methods=available_methods,
        )

    def _case(
        self, index: int, customer: CustomerProfile
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        case_id = self._id("case", index)
        profile = self.random.choices(
            FAILURE_PROFILES,
            weights=[item.weight for item in FAILURE_PROFILES],
            k=1,
        )[0]
        method = self.random.choice(PAYMENT_METHODS)
        amount = int(
            min(500_000, max(100, round(self.random.lognormvariate(7.6, 1.0))))
        )
        attempt_count = self.random.randint(1, 4)
        case_age_days = self.random.randint(0, 13)

        history_total = customer.prior_successes + customer.prior_failures
        history_rate = (
            customer.prior_successes / history_total if history_total else 0.5
        )
        base = (
            0.08
            + customer.engagement_score * 0.38
            + history_rate * 0.24
            + profile.base_adjustment
            - case_age_days * 0.012
            - (attempt_count - 1) * 0.025
        )
        method_option_lift = 0.04 if len(customer.available_methods) > 1 else 0
        probabilities = {
            "without": self._clamp(base),
            "link": self._clamp(base + profile.link_lift + method_option_lift),
            "update": self._clamp(base + profile.update_lift + method_option_lift),
            "delay": self._clamp(base + profile.delay_lift),
        }
        outcome_draw = self.random.random()

        visible = {
            "case_id": case_id,
            "customer_id": customer.customer_id,
            "payment_id": f"pay_sim_{self.config.seed}_{index:08d}",
            "amount": amount,
            "currency": "INR",
            "failure_reason": profile.reason,
            "failure_source": profile.source,
            "payment_method": method,
            "attempt_count": attempt_count,
            "case_age_days": case_age_days,
            "customer_tenure_days": customer.tenure_days,
            "prior_successes": customer.prior_successes,
            "prior_failures": customer.prior_failures,
            "engagement_score": f"{customer.engagement_score:.4f}",
            "available_methods": "|".join(customer.available_methods),
        }
        hidden = {
            "case_id": case_id,
            "would_recover_without_intervention": int(
                outcome_draw < probabilities["without"]
            ),
            "would_recover_with_recovery_link": int(
                outcome_draw < probabilities["link"]
            ),
            "would_recover_with_update_prompt": int(
                outcome_draw < probabilities["update"]
            ),
            "would_recover_after_delay": int(
                outcome_draw < probabilities["delay"]
            ),
            "p_without_intervention": f"{probabilities['without']:.6f}",
            "p_recovery_link": f"{probabilities['link']:.6f}",
            "p_update_prompt": f"{probabilities['update']:.6f}",
            "p_delay": f"{probabilities['delay']:.6f}",
        }
        return visible, hidden

    def _id(self, entity: str, index: int) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"{SIMULATOR_VERSION}:{self.config.seed}:{entity}:{index}",
            )
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return min(0.95, max(0.01, value))

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65_536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    class _atomic_csv:
        def __init__(self, path: Path, fields: tuple[str, ...]) -> None:
            self.path = path
            self.fields = fields

        def __enter__(self):
            self.temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            self.handle = self.temporary.open("w", encoding="utf-8", newline="")
            self.writer = csv.DictWriter(
                self.handle,
                fieldnames=self.fields,
                lineterminator="\n",
            )
            self.writer.writeheader()
            return self.writer

        def __exit__(self, exception_type, exception, traceback) -> None:
            self.handle.close()
            if exception_type is None:
                self.temporary.replace(self.path)
            elif self.temporary.exists():
                self.temporary.unlink()
