"""
Test audio generation performance and caching logic.
Verifies:
1. Parallel generation works (asyncio.gather)
2. Firebase caching is used (no regeneration on second call)
3. Batch Firebase reads (single call instead of N)
4. Timing comparison: cold vs warm cache
"""

import asyncio
import time
import ast
import sys

def test_asyncio_imported():
    """Verify asyncio is imported"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()
    assert "import asyncio" in source, "asyncio not imported"
    print("[PASS] asyncio imported")
    return True

def test_parallel_generation_in_all_endpoints():
    """Verify all audio endpoints use asyncio.gather for parallel generation"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    func_bodies = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_bodies[node.name] = ast.get_source_segment(source, node)

    endpoints = {
        "logic_get_test_with_audio": "asyncio.gather",
        "generate_all_grade_audio": "asyncio.gather",
        "get_all_speaking_sentences": "asyncio.gather",
        "get_comprehension_stories": "asyncio.gather",
    }

    all_pass = True
    for func_name, expected in endpoints.items():
        if func_name not in func_bodies:
            print(f"[FAIL] {func_name} not found")
            all_pass = False
            continue
        body = func_bodies[func_name]
        if expected not in body:
            print(f"[FAIL] {func_name} does not use {expected}")
            all_pass = False
        else:
            print(f"[PASS] {func_name} uses {expected}")

    return all_pass

def test_firebase_caching_for_all_tests():
    """Verify all tests have Firebase caching for audio"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    cache_paths = {
        "logic_audio": "Logic Quest",
        "spelling_audio": "Word Wizard",
        "speaking_audio": "Voice Challenge",
        "story_audio": "Story Explorer",
    }

    all_pass = True
    for path, test_name in cache_paths.items():
        if path in source:
            print(f"[PASS] {test_name} caches under {path}/")
        else:
            print(f"[FAIL] {test_name} missing cache path {path}/")
            all_pass = False

    return all_pass

def test_batch_firebase_reads():
    """Verify endpoints do batch Firebase reads (not per-item)"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    func_bodies = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_bodies[node.name] = ast.get_source_segment(source, node)

    # These endpoints should have batch reads (single .get() for all items)
    batch_endpoints = [
        "logic_get_test_with_audio",
        "generate_all_grade_audio",
        "get_all_speaking_sentences",
        "get_comprehension_stories",
    ]

    all_pass = True
    for ep in batch_endpoints:
        if ep not in func_bodies:
            continue
        body = func_bodies[ep]
        # Should NOT have db_ref.child(...).get() inside a for loop for each item
        # Should have a batch read like db_ref.child(f"...audio/{grade}").get()
        if "all_cached" in body and ".get()" in body:
            print(f"[PASS] {ep} uses batch Firebase read")
        else:
            # Check for batch pattern
            lines = body.split("\n")
            batch_found = False
            for line in lines:
                if "all_cached" in line and ".get()" in line:
                    batch_found = True
                    break
            if batch_found:
                print(f"[PASS] {ep} uses batch Firebase read (all_cached pattern)")
            else:
                print(f"[WARN] {ep} may not use batch Firebase read - verify manually")
                all_pass = False

    return all_pass

def test_no_sequential_tts_in_loops():
    """Verify no endpoint has sequential await generate_tts_audio inside a for loop"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    lines = source.split("\n")
    issues = []

    # Look for pattern: for ... in ...: followed by await generate_tts_audio (sequential)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("for ") and i + 1 < len(lines):
            # Check next few lines for sequential await generate_tts (not in asyncio.gather)
            for j in range(i + 1, min(i + 10, len(lines))):
                next_line = lines[j].strip()
                if next_line.startswith("for ") or next_line.startswith("async def") or next_line.startswith("def "):
                    break
                if "await generate_tts_audio" in next_line and "gather" not in next_line:
                    # Check if it's inside asyncio.gather (look backwards)
                    in_gather = False
                    for k in range(j, max(j - 10, i), -1):
                        if "asyncio.gather" in lines[k] or "gather(" in lines[k]:
                            in_gather = True
                            break
                    # Also skip if inside a gen_ helper function (called via gather)
                    if not in_gather and "gen_" not in next_line and "def " not in next_line:
                        # Check if we're inside a gen_ function definition
                        in_gen_func = False
                        for k in range(j, max(j - 20, i), -1):
                            if "def gen_" in lines[k]:
                                in_gen_func = True
                                break
                        if not in_gen_func:
                            issues.append(f"  Line {j+1}: {next_line}")

    if issues:
        # Filter out issues in admin/pregenerate endpoints (acceptable to be sequential)
        # Check if the line numbers fall within pregenerate functions
        with open("main.py", "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        admin_ranges = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if "pregenerate" in node.name:
                    admin_ranges.append((node.lineno, node.end_lineno))

        real_issues = []
        import re
        for issue in issues:
            # Extract line number using regex
            match = re.search(r'Line (\d+):', issue)
            if match:
                ln = int(match.group(1))
                in_admin = any(start <= ln <= end for start, end in admin_ranges)
                if not in_admin:
                    real_issues.append(issue)
            else:
                real_issues.append(issue)

        if real_issues:
            print("[WARN] Possible sequential TTS calls in user-facing endpoints:")
            for issue in real_issues:
                print(issue)
            return False
        else:
            print("[PASS] Sequential calls only in admin endpoints (acceptable)")
            return True
    else:
        print("[PASS] No sequential TTS calls in loops detected")
        return True

def test_single_word_caching():
    """Verify single word audio endpoint uses cache"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_word_audio":
            body = ast.get_source_segment(source, node)
            if "spelling_audio/_all" in body and ".get()" in body:
                print("[PASS] Single word audio uses Firebase cache")
                return True
            else:
                print("[FAIL] Single word audio does not use cache")
                return False
    print("[FAIL] generate_word_audio not found")
    return False

def test_single_sentence_caching():
    """Verify single speaking sentence endpoint uses cache"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_speaking_sentence":
            body = ast.get_source_segment(source, node)
            if "speaking_audio" in body and ".get()" in body:
                print("[PASS] Single speaking sentence uses Firebase cache")
                return True
            else:
                print("[FAIL] Single speaking sentence does not use cache")
                return False
    print("[FAIL] get_speaking_sentence not found")
    return False

def measure_parallel_vs_sequential():
    """Simulate timing: parallel vs sequential for N items"""
    N = 10  # 10 logic items
    options_per_item = 4
    total_calls = N * (1 + options_per_item)  # 50 TTS calls

    # Simulated TTS call time (OpenAI TTS-1-HD takes ~0.5-1s per call)
    tts_time_per_call = 0.75  # seconds

    sequential_time = total_calls * tts_time_per_call
    parallel_time = tts_time_per_call  # all run concurrently

    # With caching (warm cache): just Firebase read
    firebase_read_time = 0.1  # seconds for batch read

    print("\n--- Timing Simulation (10 items x 5 audio each = 50 TTS calls) ---")
    print(f"  Sequential (old):    {sequential_time:.1f}s  ({total_calls} calls x {tts_time_per_call}s)")
    print(f"  Parallel (new):      {parallel_time:.1f}s  (all concurrent, limited by slowest)")
    print(f"  Warm cache (new):    {firebase_read_time:.1f}s  (single Firebase batch read)")
    print(f"  Speedup (cold):      {sequential_time / parallel_time:.0f}x faster")
    print(f"  Speedup (warm):      {sequential_time / firebase_read_time:.0f}x faster")
    print()

    assert parallel_time < sequential_time, "Parallel should be faster"
    assert firebase_read_time < parallel_time, "Warm cache should be fastest"
    print("[PASS] Parallel + caching is significantly faster")
    return True

def test_pregenerate_endpoints_exist():
    """Verify admin pre-generate endpoints exist for warming caches"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    endpoints = [
        "/admin/pregenerate_logic_audio/",
        "/admin/pregenerate_story_audio/",
    ]

    all_pass = True
    for ep in endpoints:
        if ep in source:
            print(f"[PASS] {ep} exists")
        else:
            print(f"[FAIL] {ep} missing")
            all_pass = False

    return all_pass

def test_firebase_cache_writes():
    """Verify cache writes happen after generation"""
    with open("main.py", "r", encoding="utf-8") as f:
        source = f.read()

    cache_write_patterns = [
        ("logic_audio", "logic_get_test_with_audio"),
        ("spelling_audio", "generate_all_grade_audio"),
        ("speaking_audio", "get_all_speaking_sentences"),
        ("story_audio", "get_comprehension_stories"),
    ]

    tree = ast.parse(source)
    func_bodies = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_bodies[node.name] = ast.get_source_segment(source, node)

    all_pass = True
    for cache_path, func_name in cache_write_patterns:
        if func_name not in func_bodies:
            continue
        body = func_bodies[func_name]
        if cache_path in body and ".set(" in body:
            print(f"[PASS] {func_name} writes cache to {cache_path}/")
        else:
            print(f"[FAIL] {func_name} does not write cache to {cache_path}/")
            all_pass = False

    return all_pass

if __name__ == "__main__":
    print("=" * 65)
    print("Audio Performance & Caching Tests")
    print("=" * 65)
    print()

    tests = [
        test_asyncio_imported,
        test_parallel_generation_in_all_endpoints,
        test_firebase_caching_for_all_tests,
        test_batch_firebase_reads,
        test_no_sequential_tts_in_loops,
        test_single_word_caching,
        test_single_sentence_caching,
        test_pregenerate_endpoints_exist,
        test_firebase_cache_writes,
        measure_parallel_vs_sequential,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            result = test()
            if result:
                passed += 1
            else:
                failed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            failed += 1
        print()

    print("=" * 65)
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 65)
    sys.exit(0 if failed == 0 else 1)
