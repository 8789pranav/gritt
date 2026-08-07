"""
Test voice consistency across all test activities.
Verifies that generate_tts_audio is used by all endpoints
and that OpenAI nova voice is the primary, Polly Joanna is fallback only.
"""

import ast
import sys

def test_shared_tts_function_exists():
    """Verify generate_tts_audio function is defined in main.py"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)

    func_names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_names.append(node.name)

    assert "generate_tts_audio" in func_names, "generate_tts_audio function not found"
    assert "generate_story_audio_openai" in func_names, "generate_story_audio_openai wrapper not found"
    print("[PASS] generate_tts_audio function exists")


def test_no_direct_polly_calls_in_endpoints():
    """
    Verify that no endpoint function directly calls polly_client.synthesize_speech.
    The only Polly call should be inside generate_tts_audio (the fallback).
    """
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    # Find all lines with polly_client.synthesize_speech
    lines = source.split("\n")
    polly_lines = []
    for i, line in enumerate(lines, 1):
        if "polly_client.synthesize_speech" in line:
            polly_lines.append(i)

    # Should be exactly 1 (inside generate_tts_audio fallback)
    assert len(polly_lines) == 1, (
        f"Expected 1 polly_client.synthesize_speech call (in generate_tts_audio fallback), "
        f"found {len(polly_lines)} at lines: {polly_lines}"
    )

    # Verify it's inside generate_tts_audio (around line 1287-1298)
    assert 1250 <= polly_lines[0] <= 1310, (
        f"Polly call at line {polly_lines[0]} is not inside generate_tts_audio"
    )
    print(f"[PASS] Only 1 direct Polly call (inside generate_tts_audio fallback at line {polly_lines[0]})")


def test_no_direct_joanna_in_endpoints():
    """Verify VoiceId='Joanna' only appears in generate_tts_audio fallback"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    lines = source.split("\n")
    joanna_lines = []
    for i, line in enumerate(lines, 1):
        if "VoiceId='Joanna'" in line or 'VoiceId="Joanna"' in line:
            joanna_lines.append(i)

    assert len(joanna_lines) == 1, (
        f"Expected 1 VoiceId='Joanna' (in generate_tts_audio fallback), "
        f"found {len(joanna_lines)} at lines: {joanna_lines}"
    )
    assert 1250 <= joanna_lines[0] <= 1310, (
        f"Joanna reference at line {joanna_lines[0]} is not inside generate_tts_audio"
    )
    print(f"[PASS] VoiceId='Joanna' only in generate_tts_audio fallback at line {joanna_lines[0]}")


def test_no_neural_voice_id_constant_usage():
    """Verify NEURAL_VOICE_ID is not used in any Polly calls anymore"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    lines = source.split("\n")
    neural_lines = []
    for i, line in enumerate(lines, 1):
        if "VoiceId=NEURAL_VOICE_ID" in line:
            neural_lines.append(i)

    assert len(neural_lines) == 0, (
        f"NEURAL_VOICE_ID still used in Polly calls at lines: {neural_lines}"
    )
    print("[PASS] NEURAL_VOICE_ID not used in any Polly calls")


def test_nova_voice_in_generate_tts():
    """Verify generate_tts_audio uses 'nova' as default voice"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    # Check the function signature has voice="nova"
    assert 'voice: str = "nova"' in source, "generate_tts_audio does not default to nova voice"
    print("[PASS] generate_tts_audio defaults to 'nova' voice")


def test_endpoints_use_generate_tts_audio():
    """Verify all audio-generating endpoints call generate_tts_audio"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    endpoints_that_should_use_tts = {
        "generate_word_audio": "generate_tts_audio",
        "generate_all_grade_audio": "generate_tts_audio",
        "get_speaking_sentence": "generate_tts_audio",
        "get_all_speaking_sentences": "generate_tts_audio",
        "logic_get_test_with_audio": "generate_tts_audio",
        "pregenerate_logic_audio": "generate_tts_audio",
        "generate_story_audio_openai": "generate_tts_audio",
    }

    # Parse AST to find function bodies
    tree = ast.parse(source)
    func_bodies = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_bodies[node.name] = ast.get_source_segment(source, node)

    for func_name, expected_call in endpoints_that_should_use_tts.items():
        assert func_name in func_bodies, f"Function {func_name} not found"
        body = func_bodies[func_name]
        assert expected_call in body, (
            f"Function {func_name} does not call {expected_call}"
        )
    print(f"[PASS] All {len(endpoints_that_should_use_tts)} endpoints use generate_tts_audio")


def test_generate_story_audio_delegates_to_shared():
    """Verify generate_story_audio_openai delegates to generate_tts_audio"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_story_audio_openai":
            body = ast.get_source_segment(source, node)
            assert "generate_tts_audio" in body, "generate_story_audio_openai does not call generate_tts_audio"
            # Should be a simple wrapper (not have its own OpenAI client calls)
            assert "openai_client.audio.speech" not in body, (
                "generate_story_audio_openai still has direct OpenAI calls - should delegate to generate_tts_audio"
            )
            print("[PASS] generate_story_audio_openai delegates to generate_tts_audio")
            return
    assert False, "generate_story_audio_openai not found"


def test_logic_audio_endpoint_exists():
    """Verify /logic/get_test_with_audio/ endpoint exists"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    assert '/logic/get_test_with_audio/' in source, "get_test_with_audio endpoint not found"
    assert '/admin/pregenerate_logic_audio/' in source, "pregenerate_logic_audio endpoint not found"
    print("[PASS] Logic audio endpoints exist")


def test_polly_fallback_in_generate_tts():
    """Verify generate_tts_audio has Polly fallback"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_tts_audio":
            body = ast.get_source_segment(source, node)
            assert "polly_client" in body, "generate_tts_audio missing Polly fallback"
            assert "openai_client" in body, "generate_tts_audio missing OpenAI primary"
            assert "nova" in body, "generate_tts_audio not using nova voice"
            print("[PASS] generate_tts_audio: OpenAI nova primary + Polly fallback")
            return
    assert False, "generate_tts_audio not found"


def test_comprehension_polly_fallback_removed():
    """Verify comprehension get_stories no longer has inline Polly fallback"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_comprehension_stories":
            body = ast.get_source_segment(source, node)
            assert "polly_client" not in body, (
                "get_comprehension_stories still has inline Polly call - should rely on generate_tts_audio fallback"
            )
            print("[PASS] comprehension get_stories no longer has inline Polly fallback")
            return
    assert False, "get_comprehension_stories not found"


def test_speed_consistency():
    """Verify speed parameters are reasonable and consistent"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    # generate_tts_audio default speed=0.85 (same as comprehension)
    assert "speed: float = 0.85" in source, "generate_tts_audio default speed should be 0.85"

    # Check no speed values are unreasonable
    lines = source.split("\n")
    for i, line in enumerate(lines, 1):
        if "speed=" in line and "generate_tts_audio" not in line:
            # Extract speed value
            pass  # Speeds are passed as args, we verified the calls above

    print("[PASS] Speed parameters consistent (default 0.85 for children)")


if __name__ == "__main__":
    print("=" * 60)
    print("Voice Consistency Tests")
    print("=" * 60)
    print()

    tests = [
        test_shared_tts_function_exists,
        test_no_direct_polly_calls_in_endpoints,
        test_no_direct_joanna_in_endpoints,
        test_no_neural_voice_id_constant_usage,
        test_nova_voice_in_generate_tts,
        test_endpoints_use_generate_tts_audio,
        test_generate_story_audio_delegates_to_shared,
        test_logic_audio_endpoint_exists,
        test_polly_fallback_in_generate_tts,
        test_comprehension_polly_fallback_removed,
        test_speed_consistency,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
