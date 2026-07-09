import hashlib
import re
import time
import uuid

from agents import coordinator
import decision_engine
import patcher
import policy_engine
import predictor
import test_runner
from correctness import (
    cluster_failure,
    extract_test_intent,
    phase9_metrics,
    policy_metrics,
    simulate_patch,
    suggest_generalizations,
)
from failure_graph import FailureGraph
from memory.patterns import extract_error_type, extract_file, normalize_error_message
from memory.selector import (
    REPLAY_THRESHOLD,
    find_fix_templates,
    find_similar_cases,
    similarity_score,
)
from memory import phase9
from memory.store import add_record, load_memory
from rag.router import extract_pytest_node
from reliability import goals
from utils import extract_failure, log


MAX_STEPS = 5
REGRESSION_GUARD_LIMIT = 10
FAILED_NODE_PATTERN = re.compile(r"(?:^|\n)FAILED\s+([^\s]+::[^\s]+)")
PYTEST_STOP_REASONS = {
    2: "pytest was interrupted",
    3: "pytest had an internal error",
    4: "pytest could not run because of a usage error",
    5: "pytest collected no tests",
}


def _signature(failure):
    return (
        extract_error_type(failure),
        normalize_error_message(failure),
        extract_file(failure),
    )


def _phase4_summary(score):
    return {
        "cluster": score.get("cluster", ""),
        "intent_vector": score.get("intent", {}).get("vector", []),
        "confidence": float(score.get("confidence", 0.0) or 0.0),
        "score_signals": score.get("signals", {}),
    }


def _fallback_phase4(failure):
    intent = extract_test_intent(failure)
    return {
        "cluster": cluster_failure(failure),
        "intent_vector": intent["vector"],
        "confidence": 0.0,
        "score_signals": {},
    }


def _log_phase4(score):
    summary = _phase4_summary(score)
    intent = ",".join(summary["intent_vector"][:6]) or "none"
    signals = ",".join(
        f"{name}:{value:.2f}"
        for name, value in sorted(summary["score_signals"].items())
        if isinstance(value, (int, float))
    ) or "none"
    log(
        "PHASE4: "
        f"cluster={summary['cluster'] or 'unknown'} "
        f"intent={intent} "
        f"confidence={summary['confidence']:.2f} "
        f"signals={signals}"
    )


def _record_attempt(failure, patch, success, score=None, outcome=None):
    error_type, error_message, file = _signature(failure)
    if not error_type or not error_message:
        return
    phase4 = _phase4_summary(score or {}) if score else _fallback_phase4(failure)
    outcome = outcome or ("passed" if success else "failed")
    try:
        add_record(
            {
                "error_type": error_type,
                "error_message": error_message,
                "file": file,
                "patch": patch,
                "success": success,
                "cluster": phase4["cluster"],
                "intent_vector": phase4["intent_vector"],
                "score": phase4["confidence"],
                "confidence": phase4["confidence"],
                "score_signals": phase4["score_signals"],
                "outcome": outcome,
            }
        )
        log(
            "LEARNING: "
            f"cluster={phase4['cluster'] or 'unknown'} "
            f"confidence={phase4['confidence']:.2f} "
            f"outcome={outcome}"
        )
    except (OSError, ValueError):
        log("Memory write skipped")


def _reusable_patch(failure, memory):
    error_type, error_message, file = _signature(failure)
    if not error_type or not error_message or not file:
        return ""

    for match in find_similar_cases(failure, memory):
        case = match["record"]
        patch = case["patch"]
        if match["score"] < REPLAY_THRESHOLD or not case["success"] or not patch:
            continue
        comparable = [
            record
            for record in memory
            if record["patch"] == patch
            and similarity_score(failure, record) >= REPLAY_THRESHOLD
        ]
        latest = max(comparable, key=lambda record: record["timestamp"], default=None)
        if latest and latest["success"]:
            return patch
    return ""


def _template_patches(failure, memory):
    patches = []
    for template in find_fix_templates(failure, memory):
        patch = template["record"]["patch"]
        if patch and patch not in patches:
            patches.append(patch)
    return patches


def _finish(success, metrics, started_at):
    _finish_goal(metrics, success)
    elapsed_ms = max(0, round((time.monotonic() - started_at) * 1000))
    fix_multiplication = metrics["propagated_fixes"] / max(1, metrics["attempts"])
    prediction_total = metrics["prediction_correct"] + metrics["prediction_false_positive"]
    prediction_accuracy = (
        metrics["prediction_correct"] / prediction_total
        if prediction_total
        else 1.0
    )
    false_positive_rate = (
        metrics["prediction_false_positive"] / prediction_total
        if prediction_total
        else 0.0
    )
    actual_total = metrics["prediction_correct"] + metrics["prediction_false_negative"]
    false_negative_rate = (
        metrics["prediction_false_negative"] / actual_total
        if actual_total
        else 0.0
    )
    prevention_rate = (
        metrics["preemptive_successes"] / metrics["preemptive_attempts"]
        if metrics["preemptive_attempts"]
        else 0.0
    )
    decision_total = metrics["decision_correct"] + metrics["unnecessary_actions"]
    decision_accuracy = (
        metrics["decision_correct"] / decision_total
        if decision_total
        else 1.0
    )
    phase9_summary = phase9_metrics(metrics["phase9_records"])
    log(
        "METRICS: "
        f"attempts={metrics['attempts']} "
        f"model_calls={metrics['model_calls']} "
        f"memory_replays={metrics['memory_replays']} "
        f"context_tokens={metrics['context_tokens']} "
        f"preemptive_attempts={metrics['preemptive_attempts']} "
        f"prevention_rate={prevention_rate:.2f} "
        f"prediction_accuracy={prediction_accuracy:.2f} "
        f"false_positive_rate={false_positive_rate:.2f} "
        f"false_negative_rate={false_negative_rate:.2f} "
        f"prediction_latency_ms={metrics['prediction_latency_ms']} "
        f"decision_accuracy={decision_accuracy:.2f} "
        f"prevented_failures={metrics['prevented_failures']} "
        f"unnecessary_actions={metrics['unnecessary_actions']} "
        f"cost_saved={metrics['cost_saved']:.2f} "
        f"decision_validate_runs={metrics['decision_validate_runs']} "
        f"cumulative_reward={metrics['cumulative_reward']:.2f} "
        f"policy_improvement_rate={metrics['policy_improvement_rate']:.2f} "
        f"regret={metrics['regret']:.2f} "
        f"action_efficiency={metrics['action_efficiency']:.2f} "
        f"propagated_fixes={metrics['propagated_fixes']} "
        f"regression_rejections={metrics['regression_rejections']} "
        f"plan_success_rate={phase9_summary['plan_success_rate']:.2f} "
        f"critic_catch_rate={phase9_summary['critic_catch_rate']:.2f} "
        f"regression_avoidance_rate={phase9_summary['regression_avoidance_rate']:.2f} "
        f"strategy_roi={phase9_summary['strategy_roi']:.2f} "
        f"multi_step_efficiency={phase9_summary['multi_step_efficiency']:.2f} "
        f"evidence_gate_rejections={metrics['evidence_gate_rejections']} "
        f"tool_contract_failures={metrics['tool_contract_failures']} "
        f"goal_guard_rejections={metrics['goal_guard_rejections']} "
        f"uncertainty_downgrades={metrics['uncertainty_downgrades']} "
        f"fix_multiplication={fix_multiplication:.2f} "
        f"elapsed_ms={elapsed_ms} "
        f"passed={str(success).lower()}"
    )
    return success


def _finish_goal(metrics, success):
    goal = metrics.get("goal")
    if not goal or goal.get("state") != "active":
        return
    try:
        metrics["goal"] = goals.finish_goal(
            goal,
            "passed" if success else "failed",
        )
    except (OSError, ValueError):
        log("Phase 10 goal write skipped")


def _generated_patch(failure, repo_path, memory, run_metrics):
    generation_metrics = {}
    patches = patcher.generate_patch_candidates(
        failure,
        repo_path,
        metrics=generation_metrics,
        memory=memory,
    )
    run_metrics["model_calls"] += generation_metrics.get("model_calls", 0)
    run_metrics["context_tokens"] += generation_metrics.get("context_tokens", 0)
    return patches


def _failing_test_nodes(failure):
    nodes = set(FAILED_NODE_PATTERN.findall(failure))
    node = extract_pytest_node(failure)
    if node:
        nodes.add(f"{node[0]}::{node[1]}")
    return nodes


def _failure_count(failure):
    nodes = _failing_test_nodes(failure)
    return len(nodes) if nodes else 1


def _regression_nodes(repo_path, failure):
    failing = _failing_test_nodes(failure)
    if not failing:
        return []
    return [
        node
        for node in test_runner.collect_tests(repo_path)
        if node not in failing
    ][:REGRESSION_GUARD_LIMIT]


def _regression_guard(repo_path, failure, patch, baseline_nodes=None):
    del failure, patch
    nodes = baseline_nodes if baseline_nodes is not None else []
    if not nodes:
        return True
    result = test_runner.run_test_subset(repo_path, nodes)
    return result["passed"]


def _candidate_patches(failure, repo_path, memory, metrics, include_generated=True):
    patches = []
    remembered_patch = _reusable_patch(failure, memory)
    if remembered_patch:
        metrics["memory_replays"] += 1
        return [remembered_patch]
    template_patches = _template_patches(failure, memory)
    for patch in template_patches:
        if patch not in patches:
            metrics["memory_replays"] += 1
            patches.append(patch)
    if patches or not include_generated:
        return patches
    return _generated_patch(failure, repo_path, memory, metrics)


def _try_ranked_candidates(repo_path, failure, ranked, baseline_nodes):
    applied_candidate = False
    for candidate in ranked:
        patch = candidate["patch"]
        score = candidate.get("score", {})
        _log_phase4(score)
        if not patcher.apply_patch(repo_path, patch):
            _record_attempt(failure, patch, False, score)
            continue
        applied_candidate = True
        if not _regression_guard(repo_path, failure, patch, baseline_nodes):
            _record_attempt(failure, patch, False, score)
            patcher.revert_patch(repo_path, patch)
            log("Rejected candidate: regression guard failed")
            continue
        return patch, test_runner.run_tests(repo_path), applied_candidate
    return "", None, applied_candidate


def _log_root_causes(graph, failure):
    nodes = _failing_test_nodes(failure)
    if not nodes:
        return
    graph.update_after_test_run(failure)
    causes = graph.get_root_causes(sorted(nodes))[:3]
    if not causes:
        return
    summary = ",".join(f"{cause['node']}:{cause['score']:.2f}" for cause in causes)
    log(f"PHASE5: root_causes={summary}")


def _apply_generalizations(repo_path, patch, metrics):
    candidates = patcher.safe_generalization_patches(repo_path, patch)
    propagated = 0
    for candidate in candidates:
        if not patcher.apply_patch(repo_path, candidate):
            continue
        result = test_runner.run_tests(repo_path)
        if result["passed"]:
            propagated += 1
            metrics["propagated_fixes"] += 1
            continue
        metrics["regression_rejections"] += 1
        patcher.revert_patch(repo_path, candidate)
    suggested = max(0, len(suggest_generalizations(repo_path, patch)) - propagated)
    metrics["suggested_generalizations"] += suggested
    log(f"GENERALIZATION: propagated={propagated} suggested={suggested}")
    return propagated


def _prediction_failure_text(prediction):
    tests = "\n".join(
        f"FAILED {node} - predicted risk" for node in prediction["predicted_tests"]
    )
    modules = ", ".join(prediction["at_risk_modules"]) or "unknown"
    return f"PREEMPTIVE_RISK modules={modules}\n{tests}".strip()


def _policy_outcome(decision, actual_outcome):
    actual_cost = 0.0
    if decision["decision"] in {decision_engine.ACT, decision_engine.VALIDATE}:
        actual_cost = decision["expected_action_cost"]
    return {
        "actual_outcome": actual_outcome,
        "estimated_cost": decision["expected_action_cost"],
        "actual_cost": actual_cost,
        "failure_cost": decision["expected_failure_loss"],
        "failure_cost_saved": max(
            0.0,
            decision["expected_failure_loss"] - decision["expected_action_cost"],
        ),
    }


def _update_policy(policy, decision, outcome, metrics):
    update = policy.update(decision, outcome)
    history_entry = update.get("history_entry") or {
        "reward": update.get("reward", 0.0),
        "action_taken": decision.get("decision"),
        "best_possible_reward": outcome.get("failure_cost_saved", 0.0),
    }
    metrics["policy_history"].append(history_entry)
    computed = policy_metrics(metrics["policy_history"])
    metrics["cumulative_reward"] = computed["cumulative_reward"]
    metrics["policy_improvement_rate"] = computed["policy_improvement_rate"]
    metrics["regret"] = computed["regret"]
    metrics["action_efficiency"] = computed["action_efficiency"]
    log(
        "PHASE8: "
        f"reward={update['reward']:.2f} "
        f"epsilon={update['epsilon']:.2f} "
        f"threshold={update['threshold']:.2f} "
        f"weights={_format_policy_weights(update['weights'])}"
    )


def _format_policy_weights(weights):
    return ",".join(
        f"{name}:{value:.2f}" for name, value in sorted(weights.items())
    )


def _run_id():
    return f"run-{uuid.uuid4().hex[:16]}"


def _repository_id(repo_path):
    digest = hashlib.sha256(str(repo_path).encode("utf-8")).hexdigest()[:16]
    return f"repo-{digest}"


def _empty_simulation():
    return {
        "touched_files": [],
        "impact_score": 0.0,
        "regression_risk": 1.0,
        "pass_likelihood": 0.0,
    }


def _candidate_simulation(repo_path, candidate):
    patch = candidate.get("patch", "") if isinstance(candidate, dict) else ""
    if not patch:
        return _empty_simulation()
    try:
        simulation = simulate_patch(repo_path, patch)
    except (OSError, ValueError):
        return _empty_simulation()
    return simulation if isinstance(simulation, dict) else _empty_simulation()


def _safe_token(value, fallback):
    value = str(value or "")
    return value if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) else fallback


def _policy_outcome_from_phase9(decision, outcome):
    state = outcome["verification"].get("state")
    if state == "passed":
        actual_outcome = policy_engine.SUCCESS
    elif state in {"failed", "regressed"}:
        actual_outcome = policy_engine.FAILURE
    else:
        actual_outcome = policy_engine.NO_EFFECT
    return _policy_outcome(decision, actual_outcome)


def _record_phase9_outcome(outcome, run_id, repository_id, metrics):
    plan = outcome["plan"]
    simulation = plan.get("simulation", {})
    verification = outcome["verification"]
    actual_decision = outcome["actual_decision"]
    pre_evidence = outcome["pre_evidence"]
    state = _safe_token(verification.get("state"), "not_executed")
    reason = _safe_token(
        outcome["authorization"].get("reason") or pre_evidence.get("reason"),
        "verified" if state == "passed" else "unknown",
    )
    critic_risks = [
        _safe_token(risk, "unknown") for risk in outcome["critique"].get("risks", [])
    ]
    records = {
        "plans": {
            "run_id": run_id,
            "repository_id": repository_id,
            "plan_id": plan["plan_id"],
            "action": actual_decision["decision"],
            "strategy": plan["strategy"],
            "candidate_count": int(plan.get("candidate_count", 0) or 0),
            "reversible": bool(plan.get("reversible")),
            "executable": bool(plan.get("executable")),
            "steps": list(plan.get("steps", [])),
            "impact_score": float(simulation.get("impact_score", 0.0) or 0.0),
            "regression_risk": float(simulation.get("regression_risk", 1.0) or 1.0),
            "pass_likelihood": float(simulation.get("pass_likelihood", 0.0) or 0.0),
            "critic_risks": critic_risks,
        },
        "decisions": {
            "run_id": run_id,
            "repository_id": repository_id,
            "plan_id": plan["plan_id"],
            "proposed_action": outcome.get("proposed_action", actual_decision["decision"]),
            "action_taken": actual_decision["decision"],
            "verification_state": state,
            "evidence_score": float(pre_evidence.get("score", 0.0) or 0.0),
            "uncertainty": _safe_token(pre_evidence.get("uncertainty"), "high"),
            "reason": reason,
        },
        "strategies": {
            "run_id": run_id,
            "repository_id": repository_id,
            "plan_id": plan["plan_id"],
            "strategy": plan["strategy"],
            "action_taken": actual_decision["decision"],
            "verified": state == "passed",
            "failure_cost_saved": max(
                0.0,
                float(actual_decision.get("expected_failure_loss", 0.0) or 0.0)
                - float(actual_decision.get("expected_action_cost", 0.0) or 0.0),
            ),
            "action_cost": float(actual_decision.get("expected_action_cost", 0.0) or 0.0),
        },
    }
    if state != "passed":
        records["failures"] = {
            "run_id": run_id,
            "repository_id": repository_id,
            "plan_id": plan["plan_id"],
            "verification_state": state,
            "reason": reason,
            "tool_contract_failures": [
                _safe_token(value, "unknown")
                for value in pre_evidence.get("contract_failures", [])
            ],
        }
    try:
        for name, record in records.items():
            phase9.append_record(name, record)
    except (OSError, ValueError):
        log("Phase 9 memory write skipped")

    metrics["phase9_records"].append(
        {
            "verification_state": state,
            "reviewed": True,
            "critic_caught": bool(critic_risks),
            "applied": outcome["execution"].get("applied") is True,
            "planned_steps": len(plan.get("steps", [])),
            "completed_steps": len(plan.get("steps", [])) if state == "passed" else 0,
            "failure_cost_saved": records["strategies"]["failure_cost_saved"],
            "action_cost": records["strategies"]["action_cost"],
        }
    )
    if not pre_evidence.get("sufficient"):
        metrics["evidence_gate_rejections"] += 1
    metrics["tool_contract_failures"] += len(
        pre_evidence.get("contract_failures", [])
    )
    if not outcome["authorization"].get("authorized"):
        metrics["goal_guard_rejections"] += 1
    if actual_decision["decision"] != outcome.get("proposed_action", actual_decision["decision"]):
        metrics["uncertainty_downgrades"] += 1
    _record_goal_steps(metrics, outcome)
    log(
        "PHASE9: "
        f"plan={plan['plan_id']} strategy={plan['strategy']} "
        f"critic={'caught' if critic_risks else 'clear'} state={state}"
    )
    log(
        "PHASE10: "
        f"evidence={float(pre_evidence.get('score', 0.0) or 0.0):.2f} "
        f"uncertainty={pre_evidence.get('uncertainty', 'high')} "
        f"goal={outcome['authorization'].get('reason') or 'authorized'}"
    )


def _record_goal_steps(metrics, outcome):
    goal = metrics.get("goal")
    if not goal or goal.get("state") != "active":
        return
    steps = ["planner", "critic"]
    if outcome["execution"].get("applied"):
        steps.append("executor")
    steps.append("verifier")
    try:
        for step in steps:
            goal = goals.record_goal_step(goal, step)
        metrics["goal"] = goal
    except (OSError, ValueError):
        log("Phase 10 goal write skipped")


def _run_preemptive_prediction(
    repo_path, graph, memory, metrics, policy, run_id, repository_id, goal
):
    started = time.monotonic()
    change_set = predictor.detect_change_set(repo_path)
    if not change_set.get("files") and not change_set.get("functions"):
        return None
    graph.update_after_change(change_set)
    prediction = predictor.predict_failures(change_set, graph=graph, memory=memory)
    metrics["prediction_latency_ms"] += max(
        0, round((time.monotonic() - started) * 1000)
    )
    log(
        "PHASE6: "
        f"predicted_tests={len(prediction['predicted_tests'])} "
        f"risk={prediction['risk_score']:.2f} "
        f"confidence={prediction['confidence']:.2f}"
    )
    decision = decision_engine.evaluate(prediction, policy=policy)
    log(
        "PHASE7: "
        f"prediction=risk={prediction['risk_score']:.2f},"
        f"confidence={prediction['confidence']:.2f} "
        f"decision={decision['decision']} "
        f"expected_loss={decision['expected_failure_loss']:.2f} "
        f"action_cost={decision['expected_action_cost']:.2f} "
        f"policy_score={decision['policy_score']:.2f} "
        f"explored={str(decision['explored']).lower()}"
    )
    if decision["decision"] == decision_engine.SKIP:
        metrics["decision_skips"] += 1
        prediction["_policy_decision"] = decision
        return prediction
    if decision["decision"] == decision_engine.VALIDATE:
        metrics["decision_validate_runs"] += 1
        subset_result = {"passed": True, "output": "", "errors": ""}
        if prediction["predicted_tests"]:
            subset_result = test_runner.run_test_subset(
                repo_path,
                prediction["predicted_tests"],
            )
        outcome = (
            policy_engine.SUCCESS
            if not subset_result.get("passed", True)
            else policy_engine.NO_EFFECT
        )
        _update_policy(policy, decision, _policy_outcome(decision, outcome), metrics)
        return prediction

    metrics["preemptive_attempts"] += 1
    failure_text = _prediction_failure_text(prediction)
    generation_metrics = {}
    patches = patcher.generate_patch_candidates(
        failure_text,
        repo_path,
        metrics=generation_metrics,
        memory=memory,
    )
    metrics["model_calls"] += generation_metrics.get("model_calls", 0)
    metrics["context_tokens"] += generation_metrics.get("context_tokens", 0)
    ranked = patcher.rank_patch_candidates(repo_path, patches, failure_text, memory=memory)
    candidate = ranked[0] if ranked else None
    outcome = coordinator.run_candidate(
        repo_path,
        prediction,
        decision,
        [candidate] if candidate else [],
        _candidate_simulation(repo_path, candidate),
        phase9.load_records("strategies"),
        goal,
        1,
        patcher.apply_patch,
        lambda: {"passed": True, "output": "", "errors": "", "exit_code": 0},
        lambda: test_runner.run_tests(repo_path),
        patcher.revert_patch,
    )
    outcome["proposed_action"] = decision["decision"]
    _record_phase9_outcome(outcome, run_id, repository_id, metrics)
    prediction["_phase9_outcome"] = outcome
    prediction["_policy_decision"] = outcome["actual_decision"]
    if outcome["verification"]["state"] == "passed":
        metrics["preemptive_successes"] += 1
        metrics["prevented_failures"] += 1
        metrics["decision_correct"] += 1
        metrics["cost_saved"] += max(
            0.0,
            decision["expected_failure_loss"] - decision["expected_action_cost"],
        )
    elif outcome["verification"]["state"] in {"failed", "regressed"}:
        metrics["regression_rejections"] += 1
        metrics["unnecessary_actions"] += 1
    return prediction


def _record_prediction_outcome(prediction, result, metrics, policy=None):
    if not prediction:
        return
    calibration = predictor.update_prediction_accuracy(
        prediction,
        extract_failure(result),
    )
    metrics["prediction_correct"] += calibration["correct_predictions"]
    metrics["prediction_false_positive"] += calibration["false_positives"]
    metrics["prediction_false_negative"] += calibration["false_negatives"]
    if policy and prediction.get("_phase9_outcome"):
        decision = prediction["_policy_decision"]
        _update_policy(
            policy,
            decision,
            _policy_outcome_from_phase9(decision, prediction["_phase9_outcome"]),
            metrics,
        )
    elif policy and prediction.get("_policy_decision"):
        actual_outcome = (
            policy_engine.FAILURE
            if calibration["false_negatives"] or calibration["correct_predictions"]
            else policy_engine.NO_EFFECT
        )
        _update_policy(
            policy,
            prediction["_policy_decision"],
            _policy_outcome(prediction["_policy_decision"], actual_outcome),
            metrics,
        )


def _pytest_stop_reason(result):
    exit_code = result.get("exit_code", 1)
    if exit_code in (0, 1):
        return ""
    return PYTEST_STOP_REASONS.get(exit_code, f"pytest exited with code {exit_code}")


def run_agent(repo_path):
    started_at = time.monotonic()
    metrics = {
        "attempts": 0,
        "model_calls": 0,
        "memory_replays": 0,
        "context_tokens": 0,
        "preemptive_attempts": 0,
        "preemptive_successes": 0,
        "prediction_correct": 0,
        "prediction_false_positive": 0,
        "prediction_false_negative": 0,
        "prediction_latency_ms": 0,
        "decision_correct": 0,
        "decision_skips": 0,
        "decision_validate_runs": 0,
        "prevented_failures": 0,
        "unnecessary_actions": 0,
        "cost_saved": 0.0,
        "propagated_fixes": 0,
        "suggested_generalizations": 0,
        "regression_rejections": 0,
        "policy_history": [],
        "cumulative_reward": 0.0,
        "policy_improvement_rate": 0.0,
        "regret": 0.0,
        "action_efficiency": 0.0,
        "phase9_records": [],
        "evidence_gate_rejections": 0,
        "tool_contract_failures": 0,
        "goal_guard_rejections": 0,
        "uncertainty_downgrades": 0,
        "goal": None,
    }
    graph = FailureGraph.build(repo_path)
    memory = load_memory()
    policy = policy_engine.PolicyEngine()
    run_id = _run_id()
    repository_id = _repository_id(repo_path)
    try:
        metrics["goal"] = goals.start_goal(run_id, repository_id, MAX_STEPS)
    except (OSError, ValueError):
        log("Phase 10 goal write skipped")
        metrics["goal"] = {
            "run_id": run_id,
            "repository_id": repository_id,
            "state": "active",
            "max_steps": MAX_STEPS,
        }
    prediction = _run_preemptive_prediction(
        repo_path,
        graph,
        memory,
        metrics,
        policy,
        run_id,
        repository_id,
        metrics["goal"],
    )
    result = test_runner.run_tests(repo_path)
    _record_prediction_outcome(prediction, result, metrics, policy=policy)
    if result["passed"]:
        log("SUCCESS: tests already pass")
        return _finish(True, metrics, started_at)
    stop_reason = _pytest_stop_reason(result)
    if stop_reason:
        log(f"STOPPED: {stop_reason}")
        return _finish(False, metrics, started_at)

    for step in range(1, MAX_STEPS + 1):
        metrics["attempts"] += 1
        log(f"Fix attempt {step}/{MAX_STEPS}")
        failure = extract_failure(result)
        _log_root_causes(graph, failure)
        memory = load_memory()
        memory_patches = _candidate_patches(
            failure, repo_path, memory, metrics, include_generated=False
        )
        generated_used = False
        patches = memory_patches
        if not patches:
            patches = _generated_patch(failure, repo_path, memory, metrics)
            generated_used = True
        ranked = patcher.rank_patch_candidates(repo_path, patches, failure, memory=memory)
        if not ranked and not generated_used:
            patches = _generated_patch(failure, repo_path, memory, metrics)
            generated_used = True
            ranked = patcher.rank_patch_candidates(
                repo_path, patches, failure, memory=memory
            )
        if not ranked:
            _record_attempt(failure, "", False)
            log("STOPPED: no confident patch was produced")
            return _finish(False, metrics, started_at)

        baseline_nodes = _regression_nodes(repo_path, failure)
        patch, candidate_result, applied_candidate = _try_ranked_candidates(
            repo_path, failure, ranked, baseline_nodes
        )
        if not patch and not generated_used:
            generated = _generated_patch(failure, repo_path, memory, metrics)
            generated_used = True
            ranked = patcher.rank_patch_candidates(
                repo_path, generated, failure, memory=memory
            )
            patch, candidate_result, applied_candidate = _try_ranked_candidates(
                repo_path, failure, ranked, baseline_nodes
            )

        if patch and candidate_result:
            previous_failure_count = _failure_count(failure)
            result = candidate_result
            score = next(
                (
                    candidate.get("score", {})
                    for candidate in ranked
                    if candidate.get("patch") == patch
                ),
                {},
            )
            outcome = "passed" if result["passed"] else "failed"
            if (
                not result["passed"]
                and _failure_count(extract_failure(result)) < previous_failure_count
            ):
                outcome = "partial"
            _record_attempt(failure, patch, result["passed"], score, outcome=outcome)
            if result["passed"]:
                _apply_generalizations(repo_path, patch, metrics)
                log("SUCCESS: tests pass")
                return _finish(True, metrics, started_at)
            stop_reason = _pytest_stop_reason(result)
            if stop_reason:
                log(f"STOPPED: {stop_reason}")
                return _finish(False, metrics, started_at)
            continue

        if not applied_candidate:
            log("STOPPED: patch was unsafe or could not be applied")
            return _finish(False, metrics, started_at)
        log("STOPPED: all ranked patches were rejected")
        return _finish(False, metrics, started_at)

    log(f"STOPPED: tests still fail after {MAX_STEPS} fix attempts")
    return _finish(False, metrics, started_at)
