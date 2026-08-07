"""
End-to-end timing test for all 4 test activities.
Mocks TTS generation and Firebase to measure:
1. Cold cache (first request - generates all audio in parallel)
2. Warm cache (second request - reads from Firebase cache)
3. Verifies caching works (no regeneration on second call)
4. Verifies parallel generation (cold cache faster than sequential)
"""

import asyncio
import time
import sys
import json

# --- Mock setup ---
# We'll mock generate_tts_audio and db_ref to simulate real behavior

TTS_DELAY = 0.5  # seconds per TTS call (simulating OpenAI API latency)
FIREBASE_READ_DELAY = 0.05  # seconds per Firebase read
FIREBASE_WRITE_DELAY = 0.05  # seconds per Firebase write

# Track TTS calls to verify caching
tts_call_count = 0
tts_calls_log = []

# Mock Firebase store
firebase_store = {}

class MockFirebaseChild:
    def __init__(self, path):
        self.path = path

    def child(self, key):
        return MockFirebaseChild(f"{self.path}/{key}")

    def get(self):
        # Simulate Firebase read latency
        time.sleep(FIREBASE_READ_DELAY)
        # Firebase returns all children under a path as a dict
        # Our mock store has full paths as keys, so we need to find
        # all keys that start with this path and return them as a nested dict
        if self.path in firebase_store:
            return firebase_store[self.path]

        # Check if any stored paths are children of this path
        prefix = self.path + "/"
        children = {}
        for key, val in firebase_store.items():
            if key.startswith(prefix):
                # Extract the child key (next segment after prefix)
                remaining = key[len(prefix):]
                child_key = remaining.split("/")[0]
                if child_key not in children:
                    # If there are deeper paths, reconstruct the nested structure
                    deeper = remaining[len(child_key):]
                    if deeper.startswith("/"):
                        # Has nested path - store the value at nested location
                        nested_path = self.path + "/" + child_key + deeper
                        if child_key not in children:
                            children[child_key] = {}
                        # Walk the nested path
                        parts = deeper.strip("/").split("/")
                        current = children[child_key]
                        for p in parts[:-1]:
                            if p not in current:
                                current[p] = {}
                            current = current[p]
                        current[parts[-1]] = val
                    else:
                        # Direct child
                        children[child_key] = val

        return children if children else None

    def set(self, data):
        # Simulate Firebase write latency
        time.sleep(FIREBASE_WRITE_DELAY)
        firebase_store[self.path] = data

    def push(self):
        class MockPush:
            @property
            def key(self):
                return "mock_key_123"
        return MockPush()


db_ref = MockFirebaseChild("")

# --- Mock generate_tts_audio ---
async def generate_tts_audio(text, voice="nova", speed=0.85):
    global tts_call_count
    tts_call_count += 1
    tts_calls_log.append(text[:30])
    # Simulate API latency
    await asyncio.sleep(TTS_DELAY)
    return f"base64_audio_for_{text[:20]}"

# --- Import test data structures ---
# We need to simulate the data each test uses

# Logic Quest items (10 items, 4 options each = 50 TTS calls)
class MockOption:
    def __init__(self, index, text):
        self.index = index
        self.text = text
        self.image_url = None

class MockItem:
    def __init__(self, item_id, question_text, options, item_type="pattern", difficulty="easy"):
        self.item_id = item_id
        self.item_number = 1
        self.item_type = item_type
        self.question_text = question_text
        self.difficulty = difficulty
        self.options = options
        self.sort_config = None

logic_items = [
    MockItem(f"k1_{i:03d}", f"Question {i}: Which pattern comes next?", [
        MockOption(0, "Option A"), MockOption(1, "Option B"),
        MockOption(2, "Option C"), MockOption(3, "Option D"),
    ]) for i in range(1, 11)
]

# Spelling words (20 words x 2 audio each = 40 TTS calls)
spelling_words = [
    {"word": f"word_{i}", "sentence": f"This is word_{i} in a sentence.", "type": "regular"}
    for i in range(1, 21)
]

# Speaking sentences (8 sentences x 1 audio each = 8 TTS calls)
speaking_sentences = [
    {"id": f"k{i}", "sentence": f"Sentence number {i} for speaking test.", "word_count": 6, "difficulty": "easy"}
    for i in range(1, 9)
]

# Comprehension stories (2 stories x 1 audio each = 2 TTS calls)
comprehension_stories = [
    {"id": f"k_story_{i}", "title": f"Story {i}", "story": f"Once upon a time story {i}...", "questions": [
        {"id": f"k{i}_q1", "question": "What happened?", "options": ["A", "B", "C", "D"]}
    ]} for i in range(1, 3)
]


# --- Simulated endpoint functions (mirroring main.py logic) ---

async def simulate_logic_get_test_with_audio(grade="K-1"):
    """Simulates /logic/get_test_with_audio/ endpoint"""
    items = logic_items

    # Batch read all cached audio from Firebase in 1 call
    all_cached = db_ref.child(f"logic_audio/{grade}").get() or {}

    # Identify which items need audio generation
    items_to_generate = []
    for item in items:
        if item.item_id not in all_cached or not all_cached[item.item_id].get("question_audio"):
            items_to_generate.append(item)

    # Generate audio in parallel for all uncached items
    if items_to_generate:
        async def gen_item_audio(item):
            question_audio = await generate_tts_audio(item.question_text)
            opt_audios = await asyncio.gather(
                *[generate_tts_audio(opt.text) for opt in item.options]
            )
            return item.item_id, question_audio, list(opt_audios)

        generated = await asyncio.gather(
            *[gen_item_audio(item) for item in items_to_generate]
        )

        # Cache generated audio
        generated_map = {}
        for item_id, q_audio, o_audios in generated:
            generated_map[item_id] = {
                "question_audio": q_audio,
                "option_audios": o_audios,
            }
            if q_audio:
                db_ref.child(f"logic_audio/{grade}/{item_id}").set({
                    "question_audio": q_audio,
                    "option_audios": o_audios,
                    "voice": "nova",
                })
    else:
        generated_map = {}

    # Build response
    formatted_items = []
    for item in items:
        cached = all_cached.get(item.item_id) or generated_map.get(item.item_id, {})
        question_audio = cached.get("question_audio")
        option_audios = cached.get("option_audios", [])
        formatted_items.append({
            "item_id": item.item_id,
            "question_text": item.question_text,
            "question_audio_base64": question_audio,
            "options": [
                {"index": opt.index, "text": opt.text, "audio_base64": option_audios[i] if i < len(option_audios) else None}
                for i, opt in enumerate(item.options)
            ],
        })

    return {"success": True, "total_items": len(formatted_items), "items": formatted_items}


async def simulate_generate_all_grade_audio(grade="Kindergarten"):
    """Simulates /generate_all_grade_audio/ endpoint"""
    shuffled_words = spelling_words.copy()

    # Batch read all cached audio
    all_cached = db_ref.child(f"spelling_audio/{grade}").get() or {}

    # Identify which words need audio generation
    words_to_generate = []
    for item in shuffled_words:
        word = item["word"]
        if word not in all_cached or not all_cached[word].get("word_audio"):
            words_to_generate.append(item)

    # Generate audio in parallel
    if words_to_generate:
        async def gen_word_audio(item):
            word = item["word"]
            sentence = item["sentence"]
            word_base64 = await generate_tts_audio(word, speed=0.95)
            sentence_base64 = await generate_tts_audio(sentence, speed=1.0)
            return word, word_base64, sentence_base64

        generated = await asyncio.gather(
            *[gen_word_audio(item) for item in words_to_generate]
        )

        # Cache to Firebase
        for word, w_b64, s_b64 in generated:
            if w_b64:
                db_ref.child(f"spelling_audio/{grade}/{word}").set({
                    "word_audio": w_b64,
                    "sentence_audio": s_b64,
                    "voice": "nova",
                })
                all_cached[word] = {"word_audio": w_b64, "sentence_audio": s_b64}

    # Build response
    audio_files = []
    for item in shuffled_words:
        cached = all_cached.get(item["word"], {})
        audio_files.append({
            "word": item["word"],
            "word_audio": cached.get("word_audio"),
            "sentence_audio": cached.get("sentence_audio"),
        })

    return {"grade": grade, "audio_files": audio_files}


async def simulate_get_all_speaking_sentences(grade="Kindergarten"):
    """Simulates /speaking/get_all_sentences/ endpoint"""
    sentences = speaking_sentences.copy()

    # Batch read all cached audio
    all_cached = db_ref.child(f"speaking_audio/{grade}").get() or {}

    # Identify which sentences need audio generation
    sents_to_generate = []
    for sent in sentences:
        sid = sent["id"]
        if sid not in all_cached or not all_cached[sid].get("audio_base64"):
            sents_to_generate.append(sent)

    # Generate audio in parallel
    if sents_to_generate:
        async def gen_sent_audio(sent):
            audio = await generate_tts_audio(sent["sentence"], speed=0.9)
            return sent["id"], audio

        generated = await asyncio.gather(
            *[gen_sent_audio(sent) for sent in sents_to_generate]
        )

        # Cache to Firebase
        for sid, audio_b64 in generated:
            if audio_b64:
                db_ref.child(f"speaking_audio/{grade}/{sid}").set({
                    "audio_base64": audio_b64,
                    "voice": "nova",
                })
                all_cached[sid] = {"audio_base64": audio_b64}

    # Build response
    result_sentences = []
    for sent in sentences:
        cached = all_cached.get(sent["id"], {})
        result_sentences.append({
            "sentence_id": sent["id"],
            "sentence": sent["sentence"],
            "audio_base64": cached.get("audio_base64"),
        })

    return {"grade": grade, "total_sentences": len(result_sentences), "sentences": result_sentences}


async def simulate_get_comprehension_stories(grade="Kindergarten"):
    """Simulates /comprehension/get_stories/ endpoint"""
    stories = comprehension_stories

    # Batch read all cached audio
    all_cached = db_ref.child(f"story_audio/{grade}").get() or {}

    # Identify which stories need audio generation
    stories_to_generate = []
    for story in stories:
        sid = story["id"]
        if sid not in all_cached or not all_cached[sid].get("audio_base64"):
            stories_to_generate.append(story)

    # Generate audio in parallel
    if stories_to_generate:
        async def gen_story_audio(story):
            audio = await generate_tts_audio(story["story"], voice="nova")
            return story["id"], audio

        generated = await asyncio.gather(
            *[gen_story_audio(s) for s in stories_to_generate]
        )

        # Cache to Firebase
        for sid, audio_b64 in generated:
            if audio_b64:
                story_obj = next(s for s in stories if s["id"] == sid)
                db_ref.child(f"story_audio/{grade}/{sid}").set({
                    "audio_base64": audio_b64,
                    "title": story_obj["title"],
                    "voice": "nova",
                })
                all_cached[sid] = {"audio_base64": audio_b64}

    # Build response
    result_stories = []
    for story in stories:
        cached = all_cached.get(story["id"], {})
        result_stories.append({
            "story_id": story["id"],
            "title": story["title"],
            "story_audio_base64": cached.get("audio_base64"),
        })

    return {"success": True, "stories": result_stories}


async def simulate_sequential_tts(count):
    """Simulate old sequential TTS for comparison"""
    for _ in range(count):
        await generate_tts_audio("test")


# --- Test runner ---

async def run_test(name, sim_func, grade, expected_tts_calls):
    global tts_call_count, tts_calls_log
    tts_call_count = 0
    tts_calls_log = []

    # Cold cache (first call)
    start = time.time()
    result = await sim_func(grade)
    cold_time = time.time() - start
    cold_tts_calls = tts_call_count

    # Verify result
    assert result.get("success") or "audio_files" in result or "sentences" in result, f"{name}: invalid response"

    # Warm cache (second call)
    tts_call_count = 0
    tts_calls_log = []
    start = time.time()
    result2 = await sim_func(grade)
    warm_time = time.time() - start
    warm_tts_calls = tts_call_count

    # Verify warm cache made zero TTS calls
    assert warm_tts_calls == 0, f"{name}: warm cache made {warm_tts_calls} TTS calls (expected 0)"

    # Verify cold cache made expected number of TTS calls
    assert cold_tts_calls == expected_tts_calls, (
        f"{name}: cold cache made {cold_tts_calls} TTS calls (expected {expected_tts_calls})"
    )

    # Calculate sequential time for comparison
    sequential_time = expected_tts_calls * TTS_DELAY

    return {
        "name": name,
        "cold_time": cold_time,
        "warm_time": warm_time,
        "cold_tts_calls": cold_tts_calls,
        "warm_tts_calls": warm_tts_calls,
        "sequential_est": sequential_time,
        "speedup_cold": sequential_time / cold_time if cold_time > 0 else 0,
        "speedup_warm": sequential_time / warm_time if warm_time > 0 else 0,
    }


async def main():
    print("=" * 80)
    print("End-to-End Audio Performance Test — All 4 Test Activities")
    print("=" * 80)
    print(f"Mock TTS delay: {TTS_DELAY}s per call | Firebase read: {FIREBASE_READ_DELAY}s | Write: {FIREBASE_WRITE_DELAY}s")
    print()

    # Clear Firebase mock store
    global firebase_store
    firebase_store = {}

    tests = [
        ("Logic Quest",    simulate_logic_get_test_with_audio,       "K-1",          50),  # 10 items x (1 question + 4 options)
        ("Word Wizard",    simulate_generate_all_grade_audio,        "Kindergarten", 40),  # 20 words x (1 word + 1 sentence)
        ("Voice Challenge",simulate_get_all_speaking_sentences,      "Kindergarten", 8),   # 8 sentences x 1 audio
        ("Story Explorer", simulate_get_comprehension_stories,       "Kindergarten", 2),   # 2 stories x 1 audio
    ]

    results = []
    for name, func, grade, expected_calls in tests:
        print(f"Testing {name} (grade={grade}, expected TTS calls={expected_calls})...")
        result = await run_test(name, func, grade, expected_calls)
        results.append(result)
        print(f"  Cold: {result['cold_time']:.2f}s ({result['cold_tts_calls']} TTS calls)")
        print(f"  Warm: {result['warm_time']:.2f}s ({result['warm_tts_calls']} TTS calls)")
        print(f"  Sequential est: {result['sequential_est']:.2f}s")
        print(f"  Speedup (cold): {result['speedup_cold']:.1f}x")
        print(f"  Speedup (warm): {result['speedup_warm']:.1f}x")
        print()

    # Summary table
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Test':<20} {'TTS Calls':<12} {'Cold (s)':<12} {'Warm (s)':<12} {'Sequential (s)':<16} {'Speedup Cold':<14} {'Speedup Warm':<14}")
    print("-" * 100)
    for r in results:
        print(f"{r['name']:<20} {r['cold_tts_calls']:<12} {r['cold_time']:<12.2f} {r['warm_time']:<12.2f} {r['sequential_est']:<16.2f} {r['speedup_cold']:<14.1f} {r['speedup_warm']:<14.1f}")
    print()

    # Verify all warm cache times are fast (just Firebase read)
    for r in results:
        assert r["warm_tts_calls"] == 0, f"{r['name']}: warm cache should make 0 TTS calls"
        assert r["warm_time"] < r["cold_time"], f"{r['name']}: warm cache should be faster than cold"
        assert r["cold_time"] < r["sequential_est"], f"{r['name']}: parallel should be faster than sequential"

    print("[PASS] All tests: warm cache = 0 TTS calls")
    print("[PASS] All tests: warm cache faster than cold cache")
    print("[PASS] All tests: parallel (cold) faster than sequential")
    print()

    # Cache paths verification
    print("Firebase Cache Paths:")
    cache_paths = {
        "Logic Quest": f"/logic_audio/K-1",
        "Word Wizard": f"/spelling_audio/Kindergarten",
        "Voice Challenge": f"/speaking_audio/Kindergarten",
        "Story Explorer": f"/story_audio/Kindergarten",
    }
    for name, path in cache_paths.items():
        # Check if any keys in firebase_store start with this path
        cached_count = sum(1 for k in firebase_store if k.startswith(path + "/"))
        if cached_count > 0:
            print(f"  [PASS] {name}: {path}/ ({cached_count} items cached)")
        else:
            print(f"  [FAIL] {name}: {path}/ not cached")

    print()
    print("=" * 80)
    total_cold = sum(r["cold_time"] for r in results)
    total_warm = sum(r["warm_time"] for r in results)
    total_sequential = sum(r["sequential_est"] for r in results)
    print(f"Total time (all 4 tests):")
    print(f"  Sequential (old): {total_sequential:.2f}s")
    print(f"  Parallel cold:    {total_cold:.2f}s  ({total_sequential/total_cold:.1f}x faster)")
    print(f"  Warm cache:       {total_warm:.2f}s  ({total_sequential/total_warm:.1f}x faster)")
    print("=" * 80)

    return True


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
