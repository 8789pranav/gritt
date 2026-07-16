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
SYNTHESIS_RULES = CONFIG["synthesis_rules"]

# Item type → group mapping for Logic Quest
_LOGIC_TYPE_GROUPS = CONFIG["tests"]["logic_quest"]["item_type_groups"]

# Global tag_id -> {confidence, polarity, description, weight, test} lookup,
# built once from CONFIG so every tag's official confidence/weight is available.
_CONFIDENCE_WEIGHTS = {
    "high": SYNTHESIS_RULES["high_confidence_weight"],
    "medium": (SYNTHESIS_RULES["high_confidence_weight"] + SYNTHESIS_RULES["low_confidence_weight"]) / 2,
    "low": SYNTHESIS_RULES["low_confidence_weight"],
}

TAG_METADATA: Dict[str, Dict[str, Any]] = {}
for _test_key, _test_cfg in CONFIG["tests"].items():
    for _tag_def in _test_cfg.get("tags", []):
        TAG_METADATA[_tag_def["id"]] = {
            "test": _test_key,
            "confidence": _tag_def["confidence"],
            "polarity": _tag_def["polarity"],
            "weight": _CONFIDENCE_WEIGHTS.get(_tag_def["confidence"], 0.3),
            "description": _tag_def["description"],
        }


def get_tag_info(tag_id: str) -> Dict[str, Any]:
    """Look up official confidence/polarity/weight/description for a tag id.
    Returns a default (unknown) entry for the sentinel '0' (unanswered)."""
    return TAG_METADATA.get(tag_id, {
        "test": None, "confidence": None, "polarity": None,
        "weight": 0.0, "description": "Unanswered / no tag triggered." if tag_id == "0" else "Unknown tag.",
    })


def attach_tag_scores(tags: List[str]) -> List[Dict[str, Any]]:
    """Convert a flat list of tag ids into a list of {tag, confidence, weight, polarity} dicts."""
    return [
        {"tag": t, "confidence": get_tag_info(t)["confidence"],
         "weight": get_tag_info(t)["weight"], "polarity": get_tag_info(t)["polarity"]}
        for t in tags
    ]

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
    Derive signals for Logic Quest from raw responses (spec §6 Step 1).

    Args:
        responses: List of response dicts with keys:
            item_id, selected_answer_index, response_time_seconds, attempts, self_corrected
            Optionally: post_shift_accuracy, rule_inferred (sort tasks)
        items_lookup: Dict mapping item_id -> item info dict with keys:
            correct_answer_index, expected_latency_seconds, item_type, difficulty, primary_tag
    """
    pattern_score = 0
    relational_score = 0
    systematic_score = 0
    load_fails = 0
    rule_maintenance_fails = 0
    shift_result = "no_sort"
    rule_inferred = False
    multiple_attempts_count = 0
    fast_and_wrong_count = 0
    self_corrected_to_right_count = 0
    pattern_hard_count = 0

    latency_mult = THRESHOLDS["latency_multiplier_for_over_time"]
    fast_ratio = THRESHOLDS["fast_response_ratio_for_impulsive"]

    load_item_types = {"two_attribute_selection", "negation_two_attribute",
                       "multi_step_quantity", "two_step"}

    for resp in responses:
        item_id = resp["item_id"]
        item = items_lookup.get(item_id)
        if not item:
            continue

        is_correct = resp["selected_answer_index"] == item["correct_answer_index"]
        item_type = item.get("item_type", "")
        expected_time = item.get("expected_latency_seconds", 30)
        response_time = resp.get("response_time_seconds", 0)
        attempts = resp.get("attempts", 1)
        self_corrected = resp.get("self_corrected", False)
        difficulty = item.get("difficulty", "medium")
        primary_tag = item.get("primary_tag", "")

        # Count correct by skill group
        if is_correct:
            if primary_tag == "pattern_detection_emerging":
                pattern_score += 1
                if difficulty == "hard":
                    pattern_hard_count += 1
            elif primary_tag == "relational_reasoning_present":
                relational_score += 1
            elif primary_tag == "systematic_problem_solving":
                systematic_score += 1

        # Load fails: 2+ attribute / multi-step items wrong or slow
        if item_type in load_item_types:
            if not is_correct or response_time > expected_time * latency_mult:
                load_fails += 1

        # Rule maintenance fails: two_step items where child selected "Incorrect"
        # (index 2 = couldn't reliably apply even the first, single filter)
        if item_type == "two_step" and resp.get("selected_answer_index") == 2:
            rule_maintenance_fails += 1

        # Sort task: determine shift result
        if item_type == "sort_task":
            post_shift = resp.get("post_shift_accuracy")
            if post_shift == "correct":
                shift_result = "shifted_ok"
            elif post_shift == "incorrect":
                shift_result = "stuck"
            if resp.get("rule_inferred") is True:
                rule_inferred = True

        # Multiple attempts
        if attempts >= 2:
            multiple_attempts_count += 1

        # Fast and wrong
        if response_time < expected_time * fast_ratio and not is_correct:
            fast_and_wrong_count += 1

        # Self-corrected to right
        if self_corrected and is_correct:
            self_corrected_to_right_count += 1

    return {
        "pattern_score": pattern_score,
        "pattern_hard_count": pattern_hard_count,
        "relational_score": relational_score,
        "systematic_score": systematic_score,
        "load_fails": load_fails,
        "rule_maintenance_fails": rule_maintenance_fails,
        "shift_result": shift_result,
        "rule_inferred": rule_inferred,
        "multiple_attempts_count": multiple_attempts_count,
        "fast_and_wrong_count": fast_and_wrong_count,
        "self_corrected_to_right_count": self_corrected_to_right_count,
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
                    # String literal comparison (e.g. shift_result == shifted_ok)
                    if op in ("==", "!="):
                        lhs_str = str(lhs_val)
                        if op == "==":
                            return lhs_str == rhs
                        else:
                            return lhs_str != rhs
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


# =============================================================================
# PER-QUESTION TAGGING — one tag per question/word/sentence, "0" if unanswered
# =============================================================================

def tag_logic_per_item(responses: List[Dict], items_lookup: Dict[str, Dict]) -> List[Dict]:
    """
    Build a per-item tag entry for every item in the grade's item bank.
    Items with no matching response are marked unanswered with tag "0".

    Args:
        responses: List of raw response dicts (item_id, selected_answer_index, ...)
        items_lookup: Dict item_id -> item info (correct_answer_index, primary_tag,
                       conditional_tags, item_number)
    """
    responses_by_item = {r["item_id"]: r for r in responses}
    results = []

    for item_id, item in items_lookup.items():
        resp = responses_by_item.get(item_id)
        if resp is None:
            results.append({
                "item_id": item_id,
                "item_number": item.get("item_number", item_id),
                "answered": False,
                "selected_answer_index": None,
                "is_correct": False,
                "tags": ["0"],
            })
            continue

        selected = resp.get("selected_answer_index")
        correct_index = item.get("correct_answer_index")
        is_correct = selected == correct_index

        if is_correct:
            tag = item.get("primary_tag", "0")
        else:
            conditional_tags = item.get("conditional_tags", {})
            answer_key = f"answer_{selected}"
            if answer_key in conditional_tags:
                tag = conditional_tags[answer_key]
            elif "wrong_slow" in conditional_tags:
                tag = conditional_tags["wrong_slow"]
            else:
                tag = "0"

        results.append({
            "item_id": item_id,
            "item_number": item.get("item_number", item_id),
            "answered": True,
            "selected_answer_index": selected,
            "is_correct": is_correct,
            "tags": [tag],
        })

    return results


def tag_spelling_per_word(results: List[Dict]) -> List[Dict]:
    """
    Build a per-word tag entry using ONLY the official Word Wizard tag ids
    (see dear_parent_tags_config.json / word_wizard.tags). Each official trigger
    is evaluated against this single word's own signals (a per-item stand-in for
    the aggregate signal), so a word may earn zero, one, or several tags.
    Unattempted words (empty user_input) get tags == ["0"].
    """
    begin_keys = {"beginning", "beginning_consonant"}
    final_keys = {"final", "final_consonant"}
    vowel_keys = {"short_vowels", "short_vowel", "long_vowel", "long_vowel_patterns",
                  "other_vowel", "other_vowel_patterns"}
    digraph_keys = {"consonant_digraphs", "digraph"}
    blend_keys = {"consonant_blends", "blend"}

    output = []
    for r in results:
        word = r.get("word", "")
        user_input = (r.get("user_input") or "").strip()
        word_type = r.get("type", "regular")
        points = r.get("points", 0)
        max_points = r.get("max_points", 0)
        mistakes = r.get("mistakes", {})
        hints_used = r.get("hints_used", 0)
        time_taken = r.get("time", 999)

        if not user_input:
            output.append({"word": word, "answered": False, "is_correct": False, "tags": ["0"]})
            continue

        is_correct = points == max_points and max_points > 0
        vowel_mistake = any(k in mistakes for k in vowel_keys)
        digraph_mistake = any(k in mistakes for k in digraph_keys)
        blend_mistake = any(k in mistakes for k in blend_keys)
        begin_mistake = any(k in mistakes for k in begin_keys)
        final_mistake = any(k in mistakes for k in final_keys)

        tags = []

        if word_type == "regular":
            if not begin_mistake and not final_mistake and not vowel_mistake:
                tags.append("phonetic_strategy_strong")
            if not vowel_mistake:
                tags.append("vowel_accuracy_strong")
            else:
                tags.append("vowel_difficulty_emerging")
            if not digraph_mistake and not blend_mistake:
                tags.append("digraph_blend_competent")
            elif digraph_mistake:
                tags.append("digraph_difficulty_emerging")

        if word_type in ("sight", "nonsense"):
            if is_correct:
                tags.append("sight_word_recognition_strong")
            else:
                tags.append("sight_word_emerging")

        if hints_used > 0 and is_correct:
            tags.append("audio_support_benefit")

        if max_points >= 3 and user_input:
            tags.append("confident_attempt")

        if time_taken < 3 and not is_correct:
            tags.append("rushed_spelling")

        if not tags:
            tags = ["0"]

        output.append({
            "word": word,
            "answered": True,
            "is_correct": is_correct,
            "tags": tags,
        })

    return output


def _norm_score(score_dict: Dict, key: str = "score") -> float:
    val = score_dict.get(key, 0) if isinstance(score_dict, dict) else 0
    return val / 100.0 if val > 1 else val


def tag_speaking_per_sentence(results: List[Dict]) -> List[Dict]:
    """
    Build a per-sentence tag entry using ONLY the official Voice Challenge tag ids
    (see dear_parent_tags_config.json / voice_challenge.tags). Each official trigger
    is evaluated against this single sentence's own fluency/pronunciation/prosody
    scores and difficulty band, so a sentence may earn zero, one, or several tags.
    "Not Attempted" sentences get tags == ["0"].
    """
    output = []
    for r in results:
        sid = r.get("sentence_id", "")
        status = r.get("status", "")

        if status != "Answered":
            output.append({"sentence_id": sid, "answered": False, "tags": ["0"]})
            continue

        fluency_score = _norm_score(r.get("fluency", {}))
        pronunciation_score = _norm_score(r.get("pronunciation", {}))
        overall_score = _norm_score(r.get("overall", {}))
        grammar_score = _norm_score(r.get("grammar", {}))

        # Prosody proxy: grammar score if available, else derived from overall
        if grammar_score > 0:
            prosody_score = grammar_score
        else:
            prosody_score = max(0.0, min(1.0, 3 * overall_score - pronunciation_score - fluency_score))

        difficulty = r.get("difficulty", "medium")

        tags = []
        if fluency_score >= 0.8:
            tags.append("expressive_fluency_strong")
        elif 0.6 <= fluency_score < 0.8:
            tags.append("expressive_fluency_emerging")

        if pronunciation_score >= 0.85:
            tags.append("pronunciation_accurate")
        elif pronunciation_score < 0.7:
            tags.append("pronunciation_developing")

        if prosody_score >= 0.8:
            tags.append("prosody_strong")
        elif prosody_score < 0.6:
            tags.append("prosody_emerging")

        if difficulty == "hard" and overall_score >= 0.8:
            tags.append("complex_syntax_confident")

        if not tags:
            tags = ["0"]

        output.append({
            "sentence_id": sid,
            "answered": True,
            "fluency_score": round(fluency_score, 3),
            "pronunciation_score": round(pronunciation_score, 3),
            "prosody_score": round(prosody_score, 3),
            "tags": tags,
        })

    return output


def tag_comprehension_per_question(results: List[Dict], question_types: Dict[str, str]) -> List[Dict]:
    """
    Build a per-question tag entry using ONLY the official Story Explorer tag ids
    (see dear_parent_tags_config.json / story_explorer.tags). Each official trigger
    is evaluated against this single question's own correctness (1.0 if correct,
    0.0 if incorrect) as a per-item stand-in for the aggregate accuracy signal.
    Note: literal_comprehension has no official "weak" counterpart, and
    listening_comprehension_strong is an overall-test-level signal, so neither
    applies at single-question granularity. Unanswered questions get tags == ["0"].
    """
    output = []
    for story_result in results:
        for q in story_result.get("questions", []):
            qid = q.get("question_id", "")
            selected = q.get("selected_index", -1)
            q_type = question_types.get(qid, "literal")

            if selected is None or selected < 0:
                output.append({"question_id": qid, "answered": False, "is_correct": False, "tags": ["0"]})
                continue

            is_correct = q.get("is_correct", False)
            tags = []

            if q_type == "literal" and is_correct:
                tags.append("literal_comprehension_strong")
            elif q_type == "inferential":
                tags.append("inferential_comprehension_strong" if is_correct else "inferential_comprehension_emerging")
            elif q_type == "vocabulary":
                tags.append("vocabulary_in_context_strong" if is_correct else "vocabulary_in_context_emerging")

            if not tags:
                tags = ["0"]

            output.append({
                "question_id": qid,
                "answered": True,
                "is_correct": is_correct,
                "tags": tags,
            })

    return output
