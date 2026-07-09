from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random


ACT = "ACT"
VALIDATE = "VALIDATE"
SKIP = "SKIP"
SUCCESS = "SUCCESS"
FAILURE = "FAILURE"
NO_EFFECT = "NO_EFFECT"

FEATURES = (
    "risk_score",
    "confidence",
    "failure_frequency",
    "change_frequency",
    "centrality",
)
DEFAULT_WEIGHTS = {
    "risk_score": 0.45,
    "confidence": 0.35,
    "failure_frequency": 0.05,
    "change_frequency": 0.03,
    "centrality": 0.02,
}
DEFAULT_THRESHOLD = 0.65
DEFAULT_LOWER_THRESHOLD = 0.35
DEFAULT_LEARNING_RATE = 0.05
DEFAULT_EPSILON = 0.10
MIN_EPSILON = 0.01
EPSILON_DECAY = 0.99


def compute_reward(entry):
    action = entry.get("action_taken")
    outcome = entry.get("actual_outcome")
    actual_cost = float(entry.get("actual_cost", 0.0) or 0.0)
    failure_cost = float(entry.get("failure_cost", 0.0) or 0.0)
    failure_cost_saved = float(
        entry.get("failure_cost_saved", entry.get("failure_cost", 0.0)) or 0.0
    )

    if action == ACT:
        if outcome == SUCCESS:
            return round(failure_cost_saved, 6)
        return round(-actual_cost, 6)
    if action == VALIDATE:
        if outcome == SUCCESS:
            return round(max(0.0, failure_cost_saved - actual_cost), 6)
        if outcome == FAILURE:
            return round(-actual_cost, 6)
        return round(-actual_cost, 6)
    if action == SKIP:
        if outcome == FAILURE:
            return round(-failure_cost, 6)
        return 0.0
    return 0.0


def best_possible_reward(entry):
    failure_cost = float(entry.get("failure_cost", 0.0) or 0.0)
    failure_cost_saved = float(entry.get("failure_cost_saved", failure_cost) or 0.0)
    actual_cost = float(entry.get("actual_cost", 0.0) or 0.0)
    outcome = entry.get("actual_outcome")
    if outcome == FAILURE:
        return max(0.0, failure_cost_saved - actual_cost)
    if outcome == SUCCESS:
        return failure_cost_saved
    return 0.0


def default_history_path():
    override = os.environ.get("OPENCLAW_POLICY_HISTORY_PATH")
    if override:
        return Path(override).expanduser()
    return Path("memory") / "policy_history.jsonl"


def default_state_path():
    override = os.environ.get("OPENCLAW_POLICY_STATE_PATH")
    if override:
        return Path(override).expanduser()
    return Path("memory") / "policy_state.json"


class PolicyEngine:
    def __init__(
        self,
        path=None,
        state_path=None,
        weights=None,
        threshold=None,
        lower_threshold=None,
        learning_rate=DEFAULT_LEARNING_RATE,
        epsilon=DEFAULT_EPSILON,
        random_seed=None,
    ):
        self.path = Path(path) if path is not None else default_history_path()
        self.state_path = (
            Path(state_path) if state_path is not None else default_state_path()
        )
        self.learning_rate = float(learning_rate)
        self._random = random.Random(random_seed)
        self.weights = DEFAULT_WEIGHTS.copy()
        self.threshold = DEFAULT_THRESHOLD
        self.lower_threshold = DEFAULT_LOWER_THRESHOLD
        self.epsilon = float(epsilon)
        self._load_state()
        if weights is not None:
            self.weights.update({name: float(value) for name, value in weights.items()})
        if threshold is not None:
            self.threshold = float(threshold)
        if lower_threshold is not None:
            self.lower_threshold = float(lower_threshold)

    def predict(self, features):
        prepared = prepare_features(features)
        score = self.score(prepared)
        explored = self._random.random() < self.epsilon
        if explored:
            decision = self._random.choice([ACT, VALIDATE, SKIP])
        elif score > self.threshold:
            decision = ACT
        elif score > self.lower_threshold:
            decision = VALIDATE
        else:
            decision = SKIP
        return {
            "decision": decision,
            "features": prepared,
            "policy_score": score,
            "threshold": round(self.threshold, 6),
            "lower_threshold": round(self.lower_threshold, 6),
            "epsilon": round(self.epsilon, 6),
            "explored": explored,
        }

    def score(self, features):
        normalized = normalize_features(features)
        value = sum(self.weights[name] * normalized[name] for name in FEATURES)
        return round(value, 6)

    def update(self, decision, outcome):
        entry = build_history_entry(decision, outcome)
        reward = compute_reward(entry)
        predicted_value = float(decision.get("policy_score", 0.0) or 0.0)
        error = reward - predicted_value
        normalized = normalize_features(entry)
        for name in FEATURES:
            updated = self.weights[name] + self.learning_rate * error * normalized[name]
            self.weights[name] = round(max(-2.0, min(2.0, updated)), 6)
        self._adjust_thresholds(entry["action_taken"], reward)
        self.epsilon = round(max(MIN_EPSILON, self.epsilon * EPSILON_DECAY), 6)
        entry["reward"] = round(reward, 6)
        entry["predicted_value"] = round(predicted_value, 6)
        entry["best_possible_reward"] = round(best_possible_reward(entry), 6)
        entry["updated_weights"] = self.weights.copy()
        entry["updated_threshold"] = round(self.threshold, 6)
        entry["updated_lower_threshold"] = round(self.lower_threshold, 6)
        entry["updated_epsilon"] = self.epsilon
        self._append_history(entry)
        self._save_state()
        return {
            "reward": entry["reward"],
            "weights": self.weights.copy(),
            "epsilon": self.epsilon,
            "threshold": entry["updated_threshold"],
            "lower_threshold": entry["updated_lower_threshold"],
            "history_entry": entry.copy(),
        }

    def _adjust_thresholds(self, action, reward):
        step = min(0.03, abs(reward) * self.learning_rate * 0.05)
        if action == ACT and reward < 0:
            self.threshold += step
        elif action in {ACT, SKIP} and reward > 0:
            self.threshold -= step
        if action == SKIP and reward < 0:
            self.lower_threshold -= step
        elif action == VALIDATE and reward < 0:
            self.lower_threshold += step
        self.threshold = round(max(0.05, min(1.5, self.threshold)), 6)
        self.lower_threshold = round(
            max(0.0, min(self.threshold - 0.01, self.lower_threshold)),
            6,
        )

    def _load_state(self):
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        weights = data.get("weights", {})
        if isinstance(weights, dict):
            for name in FEATURES:
                if isinstance(weights.get(name), (int, float)):
                    self.weights[name] = float(weights[name])
        for attr in ("threshold", "lower_threshold", "epsilon"):
            if isinstance(data.get(attr), (int, float)):
                setattr(self, attr, float(data[attr]))

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "weights": self.weights,
            "threshold": self.threshold,
            "lower_threshold": self.lower_threshold,
            "epsilon": self.epsilon,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.state_path)

    def _append_history(self, entry):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def prepare_features(features):
    centrality = _number(
        features,
        "centrality",
        _number(features, "dependency_centrality", 0.0),
    )
    return {
        "risk_score": _number(features, "risk_score", 0.0),
        "confidence": _number(features, "confidence", 0.0),
        "failure_frequency": _number(features, "failure_frequency", 0.0),
        "change_frequency": _number(features, "change_frequency", 0.0),
        "centrality": centrality,
    }


def normalize_features(features):
    return {
        "risk_score": max(0.0, min(1.0, _number(features, "risk_score", 0.0))),
        "confidence": max(0.0, min(1.0, _number(features, "confidence", 0.0))),
        "failure_frequency": max(
            0.0, min(1.0, _number(features, "failure_frequency", 0.0) / 10)
        ),
        "change_frequency": max(
            0.0, min(1.0, _number(features, "change_frequency", 0.0) / 10)
        ),
        "centrality": max(0.0, min(1.0, _number(features, "centrality", 0.0) / 10)),
    }


def build_history_entry(decision, outcome):
    features = decision.get("features", {})
    entry = prepare_features(features)
    entry.update(
        {
            "action_taken": decision.get("decision", SKIP),
            "estimated_cost": _number(outcome, "estimated_cost", 0.0),
            "actual_outcome": outcome.get("actual_outcome", NO_EFFECT),
            "actual_cost": _number(outcome, "actual_cost", 0.0),
            "failure_cost": _number(outcome, "failure_cost", 0.0),
            "failure_cost_saved": _number(outcome, "failure_cost_saved", 0.0),
            "policy_score": _number(decision, "policy_score", 0.0),
            "explored": bool(decision.get("explored", False)),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    return entry


def load_history(path=None):
    history_path = Path(path) if path is not None else default_history_path()
    records = []
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _number(mapping, key, default):
    if not isinstance(mapping, dict):
        return float(default)
    try:
        return float(mapping.get(key, default) or 0.0)
    except (TypeError, ValueError):
        return float(default)
