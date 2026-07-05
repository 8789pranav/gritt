"""
Dear Parent — Phase 2 Tagging Engine
=====================================
Deterministic, rule-based tag emitter.
Converts raw test responses into a per-test array of tag objects.

Flow:
  1. Score raw responses → derived_signals (per test)
  2. Evaluate each tag's trigger condition against signals
  3. Emit tag objects: { id, confidence, polarity, evidence }
  4. Return per-test tag array for synthesis engine (Phase 3)

No AI. Transparent, testable, every tag traces to a specific signal.
Thresholds are in dear_parent_tags_config.json.
"""

import json
from typing import List, Dict, Any, Optional
from pathlib import Path

# Load config at module level
_CONFIG_PATH = Path(__file__).parent / "dear_parent_tags_config.json"
with open(_CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

THRESHOLDS = CONFIG["thresholds"]

# Item type → group mapping for Logic Quest
_LOGIC_TYPE_GROUPS = CONFIG["tests"]["logic_quest"]["item_type_groups"]

def _classify_logic_item(item_type: str) -> str:
    """Map an item_type string to its group (pattern/relational/multistep/self_report)."""
    for group, types in _LOGIC_TYPE_GROUPS.items():
        if item_type in types:
            return group
    return "unknown"


# =============================================================================
# SIGNAL DERIVATION — one function per test
# =============================================================================

def derive_logic_signals(responses: List[Dict], items_lookup: Dict[str, Dict]) -> Dict[str, Any]:
    """
    Derive signals for Logic Quest from raw responses.

    Args:
        responses: List of response dicts with keys:
            item_id, selected_answer_index, response_time_seconds, attempts, self_corrected
        items_lookup: Dict mapping item_id -> item info dict with keys:
            correct_answer_index, expected_latency_seconds, item_type
    """
    pattern_correct = 0
    relational_correct = 0
    multistep_correct = 0
    items_self_corrected = 0
    items_over_time_incorrect = 0
    items_multiple_attempts = 0
    fast_inaccurate_items = 0
    selfreport_negative = 0

    latency_mult = THRESHOLDS["latency_multiplier_for_over_time"]
    fast_ratio = THRESHOLDS["fast_response_ratio_for_impulsive"]

    for resp in responses:
        item_id = resp["item_id"]
        item = items_lookup.get(item_id)
        if not item:
            continue

        is_correct = resp["selected_answer_index"] == item["correct_answer_index"]
        group = _classify_logic_item(item["item_type"])
        expected_time = item.get("expected_latency_seconds", 30)
        response_time = resp.get("response_time_seconds", 0)
        attempts = resp.get("attempts", 1)
        self_corrected = resp.get("self_corrected", False)

        # Count correct by group
        if is_correct:
            if group == "pattern":
                pattern_correct += 1
            elif group == "relational":
                relational_correct += 1
            elif group == "multistep":
                multistep_correct += 1

        # Self-correction
        if self_corrected:
            items_self_corrected += 1

        # Over-time AND incorrect
        if response_time > expected_time * latency_mult and not is_correct:
            items_over_time_incorrect += 1

        # Multiple attempts
        if attempts > 1:
            items_multiple_attempts += 1

        # Fast + inaccurate (responded in less than half expected time, got it wrong)
        if response_time < expected_time * fast_ratio and not is_correct:
            fast_inaccurate_items += 1

        # Self-report negative (category_shift/strategy items answered negatively)
        if group == "self_report" and not is_correct:
            selfreport_negative += 1

    return {
        "pattern_items_correct": pattern_correct,
        "relational_items_correct": relational_correct,
        "multistep_items_correct": multistep_correct,
        "items_self_corrected": items_self_corrected,
        "items_over_time_incorrect": items_over_time_incorrect,
        "items_multiple_attempts": items_multiple_attempts,
        "fast_inaccurate_items": fast_inaccurate_items,
        "selfreport_negative": selfreport_negative,
    }


def derive_spelling_signals(results: List[Dict], grade: str) -> Dict[str, Any]:
    """
    Derive signals for Word Wizard from scored spelling results.

    Args:
        results: List of per-word result dicts with keys:
            word, user_input, type (regular/sight), points, max_points,
            mistakes (dict of feature->value), time, hints_used
        grade: Grade string (Kindergarten, First, Second, Third)
    """
    regular_results = [r for r in results if r.get("type") == "regular"]
    sight_results = [r for r in results if r.get("type") == "sight"]

    # Feature accuracy — count correct features vs total features
    begin_total = 0
    begin_correct = 0
    final_total = 0
    final_correct = 0
    vowel_total = 0
    vowel_correct = 0
    vowel_error_count = 0
    digraph_total = 0
    digraph_correct = 0
    digraph_error_count = 0
    blend_total = 0
    blend_correct = 0

    # Feature key mapping varies by grade
    begin_keys = {"beginning", "beginning_consonant"}
    final_keys = {"final", "final_consonant"}
    vowel_keys = {"short_vowels", "short_vowel", "long_vowel", "long_vowel_patterns", "other_vowel", "other_vowel_patterns"}
    digraph_keys = {"consonant_digraphs", "digraph"}
    blend_keys = {"consonant_blends", "blend"}

    for r in regular_results:
        mistakes = r.get("mistakes", {})
        # We infer which features were tested by checking max_points > 0
        # But more directly, iterate over mistake keys to find errors
        for key in mistakes:
            if key in begin_keys:
                begin_total += 1
                # It's in mistakes → error
            elif key in final_keys:
                final_total += 1
            elif key in vowel_keys:
                vowel_total += 1
                vowel_error_count += 1
            elif key in digraph_keys:
                digraph_total += 1
                digraph_error_count += 1
            elif key in blend_keys:
                blend_total += 1

        # Count correct features: points earned = features correct
        # max_points = total features testable for this word
        points = r.get("points", 0)
        max_pts = r.get("max_points", 0)
        correct_features = points
        error_features = max_pts - points

        # We need total features by type. Since we only have mistake keys for errors,
        # estimate totals from max_points proportionally, but better:
        # for accuracy, count all words that HAVE that feature and track hit/miss.

    # Simpler approach: calculate from aggregated error analysis pattern
    # Use points/max_points for overall feature accuracy
    total_regular_points = sum(r.get("points", 0) for r in regular_results)
    total_regular_max = sum(r.get("max_points", 0) for r in regular_results)

    # For feature-level accuracy, count words with errors in each category
    words_with_begin_feature = 0
    words_with_final_feature = 0
    words_with_vowel_feature = 0
    words_with_digraph_feature = 0
    words_with_blend_feature = 0
    begin_errors = 0
    final_errors = 0
    vowel_errors = 0
    digraph_errors = 0
    blend_errors = 0

    for r in regular_results:
        mistakes = r.get("mistakes", {})
        # Assume every regular word tests beginning and final at minimum
        words_with_begin_feature += 1
        words_with_final_feature += 1
        words_with_vowel_feature += 1  # All words have vowels

        if any(k in mistakes for k in begin_keys):
            begin_errors += 1
        if any(k in mistakes for k in final_keys):
            final_errors += 1
        if any(k in mistakes for k in vowel_keys):
            vowel_errors += 1
        if any(k in mistakes for k in digraph_keys):
            digraph_errors += 1
            words_with_digraph_feature += 1
        if any(k in mistakes for k in blend_keys):
            blend_errors += 1
            words_with_blend_feature += 1

    n_regular = len(regular_results) or 1
    beginning_accuracy = 1.0 - (begin_errors / n_regular)
    final_accuracy = 1.0 - (final_errors / n_regular)
    vowel_accuracy = 1.0 - (vowel_errors / n_regular)
    digraph_accuracy = 1.0 - (digraph_errors / max(words_with_digraph_feature, 1))
    blend_accuracy = 1.0 - (blend_errors / max(words_with_blend_feature, 1))

    # Sight word accuracy
    sight_correct = sum(1 for r in sight_results if r.get("points", 0) == r.get("max_points", 1))
    sight_total = len(sight_results) or 1
    sight_word_accuracy = sight_correct / sight_total

    # Regular word accuracy (full word correct)
    regular_correct = sum(1 for r in regular_results if r.get("points", 0) == r.get("max_points", 1))
    regular_word_accuracy = regular_correct / n_regular

    # Audio support benefit: check if hints_used > 0 correlates with correct answers
    # Heuristic: if any word was corrected after hint, this is true
    improved_with_audio = any(
        r.get("hints_used", 0) > 0 and r.get("points", 0) == r.get("max_points", 0)
        for r in results
    )

    # Hard words attempted (words with max_points >= 3 for regular)
    hard_words = [r for r in regular_results if r.get("max_points", 0) >= 3]
    hard_attempted = sum(1 for r in hard_words if r.get("user_input", "").strip() != "")
    hard_words_attempted_ratio = hard_attempted / max(len(hard_words), 1)

    # Fast slips: answered quickly (< 3 seconds) but got it wrong for simple words
    fast_slips = sum(
        1 for r in results
        if r.get("time", 999) < 3 and r.get("points", 0) < r.get("max_points", 1)
    )

    return {
        "beginning_accuracy": round(beginning_accuracy, 3),
        "final_accuracy": round(final_accuracy, 3),
        "vowel_accuracy": round(vowel_accuracy, 3),
        "vowel_error_count": vowel_errors,
        "digraph_accuracy": round(digraph_accuracy, 3),
        "blend_accuracy": round(blend_accuracy, 3),
        "digraph_error_count": digraph_errors,
        "sight_word_accuracy": round(sight_word_accuracy, 3),
        "regular_word_accuracy": round(regular_word_accuracy, 3),
        "improved_with_audio": improved_with_audio,
        "hard_words_attempted_ratio": round(hard_words_attempted_ratio, 3),
        "fast_slips": fast_slips,
    }


def derive_speaking_signals(results: List[Dict]) -> Dict[str, Any]:
    """
    Derive signals for Voice Challenge from scored speaking results.

    Args:
        results: List of per-sentence result dicts with keys:
            sentence_id, status, pronunciation, fluency, overall,
            speaking_rate, grammar, original_sentence, difficulty (from sentence bank)
    """
    min_sentences = THRESHOLDS.get("min_sentences_for_speaking_tag", 3)
    borderline_low = THRESHOLDS.get("borderline_score_low", 0.55)
    borderline_high = THRESHOLDS.get("borderline_score_high", 0.65)

    answered = [r for r in results if r.get("status") == "Answered"]
    if len(answered) < min_sentences:
        # Not enough data to emit any tags
        return {
            "avg_fluency": 0.0,
            "avg_pronunciation": 0.0,
            "avg_prosody": 0.0,
            "flat_delivery": False,
            "hard_band_avg": 0.0,
            "_insufficient_data": True,
        }

    # Extract scores (normalize to 0-1 if they come as 0-100)
    def _norm(score_dict, key="score"):
        val = 0
        if isinstance(score_dict, dict):
            val = score_dict.get(key, 0)
        if val > 1:
            val = val / 100.0
        return val

    fluency_scores = [_norm(r.get("fluency", {})) for r in answered]
    pronunciation_scores = [_norm(r.get("pronunciation", {})) for r in answered]
    # Prosody: may be in fluency or separate; use overall - (pronunciation + fluency)/2 as proxy
    # or check if grammar/overall has prosody info
    overall_scores = [_norm(r.get("overall", {})) for r in answered]

    avg_fluency = sum(fluency_scores) / len(fluency_scores)
    avg_pronunciation = sum(pronunciation_scores) / len(pronunciation_scores)

    # Prosody: use grammar score as proxy if available, otherwise estimate from overall
    # The AI analysis returns grammar which captures expressive language quality
    grammar_scores = [_norm(r.get("grammar", {})) for r in answered]
    avg_grammar = sum(grammar_scores) / len(grammar_scores) if grammar_scores else 0

    # If grammar scores are available (> 0), use them as prosody proxy
    # Otherwise estimate prosody as the "expression" portion of overall
    if avg_grammar > 0:
        avg_prosody = avg_grammar
    else:
        # Estimate: prosody is the part of overall not explained by pronunciation + fluency
        # overall ≈ (pronunciation + fluency + prosody) / 3 → prosody ≈ 3*overall - pronunciation - fluency
        avg_prosody = max(0, min(1.0, 3 * (sum(overall_scores) / len(overall_scores)) - avg_pronunciation - avg_fluency))

    # Flat delivery: only flag when overall performance is below strong threshold
    # A strong speaker (overall >= 0.8) should NOT be flagged as flat even with low variance
    avg_overall = sum(overall_scores) / len(overall_scores) if overall_scores else 0
    flat_delivery = avg_prosody < 0.6 and avg_overall < 0.8

    # Hard band: sentences marked difficulty=hard
    hard_sentences = [r for r in answered if _get_difficulty(r) == "hard"]
    hard_band_avg = 0.0
    if hard_sentences:
        hard_overall = [_norm(r.get("overall", {})) for r in hard_sentences]
        hard_band_avg = sum(hard_overall) / len(hard_overall)

    return {
        "avg_fluency": round(avg_fluency, 3),
        "avg_pronunciation": round(avg_pronunciation, 3),
        "avg_prosody": round(avg_prosody, 3),
        "flat_delivery": flat_delivery,
        "hard_band_avg": round(hard_band_avg, 3),
    }


def _get_difficulty(result: Dict) -> str:
    """Extract difficulty from a speaking result. May be nested or flat."""
    # Check if the sentence metadata is included
    return result.get("difficulty", "medium")


def derive_comprehension_signals(results: List[Dict], question_types: Dict[str, str]) -> Dict[str, Any]:
    """
    Derive signals for Story Explorer from scored comprehension results.

    Args:
        results: List of story result dicts, each containing 'questions' list
            where each question has: question_id, is_correct
        question_types: Dict mapping question_id -> question type
            ("literal", "inferential", "vocabulary")
    """
    literal_correct = 0
    literal_total = 0
    inferential_correct = 0
    inferential_total = 0
    vocabulary_correct = 0
    vocabulary_total = 0
    overall_correct = 0
    overall_total = 0

    for story_result in results:
        questions = story_result.get("questions", [])
        for q in questions:
            qid = q.get("question_id", "")
            is_correct = q.get("is_correct", False)
            q_type = question_types.get(qid, "literal")  # default to literal

            overall_total += 1
            if is_correct:
                overall_correct += 1

            if q_type == "literal":
                literal_total += 1
                if is_correct:
                    literal_correct += 1
            elif q_type == "inferential":
                inferential_total += 1
                if is_correct:
                    inferential_correct += 1
            elif q_type == "vocabulary":
                vocabulary_total += 1
                if is_correct:
                    vocabulary_correct += 1

    literal_accuracy = literal_correct / max(literal_total, 1)
    inferential_accuracy = inferential_correct / max(inferential_total, 1)
    vocabulary_accuracy = vocabulary_correct / max(vocabulary_total, 1)
    overall_accuracy = overall_correct / max(overall_total, 1)

    literal_inferential_gap = literal_accuracy - inferential_accuracy

    return {
        "literal_accuracy": round(literal_accuracy, 3),
        "inferential_accuracy": round(inferential_accuracy, 3),
        "vocabulary_accuracy": round(vocabulary_accuracy, 3),
        "overall_accuracy": round(overall_accuracy, 3),
        "literal_inferential_gap": round(literal_inferential_gap, 3),
    }


# =============================================================================
# TAG EVALUATION ENGINE — generic, config-driven
# =============================================================================

def _evaluate_trigger(trigger: str, signals: Dict[str, Any]) -> bool:
    """
    Evaluate a trigger expression against a signals dict.
    Supports: >=, <=, ==, <, >, !=, AND, OR
    All comparisons are numeric or boolean.
    """
    # Handle AND/OR
    if " AND " in trigger:
        parts = trigger.split(" AND ")
        return all(_evaluate_trigger(p.strip(), signals) for p in parts)
    if " OR " in trigger:
        parts = trigger.split(" OR ")
        return any(_evaluate_trigger(p.strip(), signals) for p in parts)

    # Parse single comparison
    for op in [">=", "<=", "==", "!=", ">", "<"]:
        if op in trigger:
            lhs, rhs = trigger.split(op, 1)
            lhs = lhs.strip()
            rhs = rhs.strip()

            # Resolve LHS value from signals
            lhs_val = signals.get(lhs)
            if lhs_val is None:
                return False

            # Resolve RHS — could be another signal key or a literal
            if rhs in signals:
                rhs_val = signals[rhs]
            elif rhs.lower() == "true":
                rhs_val = True
            elif rhs.lower() == "false":
                rhs_val = False
            else:
                try:
                    rhs_val = float(rhs)
                except ValueError:
                    return False

            # Normalize booleans for comparison
            if isinstance(lhs_val, bool):
                if op == "==":
                    return lhs_val == rhs_val
                elif op == "!=":
                    return lhs_val != rhs_val
                return False

            # Numeric comparison
            lhs_num = float(lhs_val)
            rhs_num = float(rhs_val) if not isinstance(rhs_val, bool) else (1.0 if rhs_val else 0.0)

            if op == ">=":
                return lhs_num >= rhs_num
            elif op == "<=":
                return lhs_num <= rhs_num
            elif op == "==":
                return lhs_num == rhs_num
            elif op == "!=":
                return lhs_num != rhs_num
            elif op == ">":
                return lhs_num > rhs_num
            elif op == "<":
                return lhs_num < rhs_num

    return False


def emit_tags(test_key: str, signals: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Evaluate all tag triggers for a test and emit matching tag objects.

    Args:
        test_key: One of "logic_quest", "word_wizard", "voice_challenge", "story_explorer"
        signals: Derived signals dict for that test

    Returns:
        List of tag objects: [{ id, confidence, polarity, evidence }, ...]
    """
    if signals.get("_insufficient_data"):
        return []

    test_config = CONFIG["tests"].get(test_key)
    if not test_config:
        raise ValueError(f"Unknown test key: {test_key}")

    tags = []
    for tag_def in test_config["tags"]:
        trigger = tag_def["trigger"]
        if _evaluate_trigger(trigger, signals):
            tags.append({
                "id": tag_def["id"],
                "confidence": tag_def["confidence"],
                "polarity": tag_def["polarity"],
                "evidence": _build_evidence(trigger, signals),
            })

    return tags


def _build_evidence(trigger: str, signals: Dict[str, Any]) -> Dict[str, Any]:
    """Build an evidence dict showing which signal values fired the trigger."""
    evidence = {"trigger": trigger}
    # Extract signal keys referenced in the trigger
    for key in signals:
        if key in trigger and not key.startswith("_"):
            evidence[key] = signals[key]
    return evidence


# =============================================================================
# TOP-LEVEL ORCHESTRATOR
# =============================================================================

def tag_logic_test(responses: List[Dict], items_lookup: Dict[str, Dict]) -> List[Dict]:
    """Full pipeline: raw logic responses → tag array."""
    signals = derive_logic_signals(responses, items_lookup)
    return emit_tags("logic_quest", signals)


def tag_spelling_test(results: List[Dict], grade: str) -> List[Dict]:
    """Full pipeline: scored spelling results → tag array."""
    signals = derive_spelling_signals(results, grade)
    return emit_tags("word_wizard", signals)


def tag_speaking_test(results: List[Dict]) -> List[Dict]:
    """Full pipeline: scored speaking results → tag array."""
    signals = derive_speaking_signals(results)
    return emit_tags("voice_challenge", signals)


def tag_comprehension_test(
    results: List[Dict],
    question_types: Dict[str, str],
) -> List[Dict]:
    """Full pipeline: scored comprehension results → tag array."""
    signals = derive_comprehension_signals(results, question_types)
    return emit_tags("story_explorer", signals)


def tag_all_tests(
    logic_responses: Optional[List[Dict]] = None,
    logic_items_lookup: Optional[Dict[str, Dict]] = None,
    spelling_results: Optional[List[Dict]] = None,
    spelling_grade: Optional[str] = None,
    speaking_results: Optional[List[Dict]] = None,
    comprehension_results: Optional[List[Dict]] = None,
    comprehension_question_types: Optional[Dict[str, str]] = None,
) -> Dict[str, List[Dict]]:
    """
    Run tagging for all available tests. Pass None for tests not taken.
    Returns: { "logic_quest": [...], "word_wizard": [...], ... }
    Ready for synthesis engine (Phase 3).
    """
    output = {}

    if logic_responses is not None and logic_items_lookup is not None:
        output["logic_quest"] = tag_logic_test(logic_responses, logic_items_lookup)

    if spelling_results is not None and spelling_grade is not None:
        output["word_wizard"] = tag_spelling_test(spelling_results, spelling_grade)

    if speaking_results is not None:
        output["voice_challenge"] = tag_speaking_test(speaking_results)

    if comprehension_results is not None and comprehension_question_types is not None:
        output["story_explorer"] = tag_comprehension_test(
            comprehension_results, comprehension_question_types
        )

    return output
