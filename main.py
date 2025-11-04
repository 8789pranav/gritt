from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, auth, db
import requests
import uuid
import os
import base64
import json
from datetime import datetime
import boto3
from fastapi.responses import Response
import random

# Initialize FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# Load environment variables
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL")
FIREBASE_CRED_BASE64 = os.getenv("FIREBASE_CRED_BASE64")
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    try:
        if FIREBASE_CRED_BASE64:
            cred_json = base64.b64decode(FIREBASE_CRED_BASE64).decode('utf-8')
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
        else:
            raise ValueError("FIREBASE_CRED_BASE64 environment variable is not set")
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': FIREBASE_DB_URL
        })
        db_ref = db.reference()
    except Exception as e:
        print(f"Failed to initialize Firebase: {str(e)}")
        raise Exception(f"Firebase initialization failed: {str(e)}")

# Initialize AWS Polly client
polly_client = boto3.client(
    'polly',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# Data models
class GradeInput(BaseModel):
    grade: str

class WordInput(BaseModel):
    word: str
    user_input: str
    type: str
    time: float = 0.0
    hints_used: int = 0

class SubmitWordsRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str
    words: List[WordInput]

class UserCreate(BaseModel):
    idToken: str
    email: str
    name: str
    password: str | None = None  # ← Optional (can be null or omitted)

class UserLogin(BaseModel):
    email: str
    password: str

class UserDetails(BaseModel):
    idToken: str
    email: str
    name: str
    age: int

class ChildCreate(BaseModel):
    idToken: str
    name: str
    age: int
    grade: str

class ChildDetails(BaseModel):
    child_id: str
    name: str
    age: int
    grade: str

class DeleteChildRequest(BaseModel):
    idToken: str
    child_id: str

class ChildDetailsWithScores(BaseModel):
    child_id: str
    name: str
    age: int
    grade: str
    scores: List[Dict]

class AudioRequest(BaseModel):
    idToken: str
    text: str

class GetDetailsRequest(BaseModel):
    idToken: str

class CompleteResultRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str = None

# Word lists
word_lists = {
    "Kindergarten": {
        "regular_words": {
            # Short a
            "cat": {"beginning": "c", "final": "t", "short_vowels": "a", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The cat chased the mouse."},
            "mat": {"beginning": "m", "final": "t", "short_vowels": "a", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Sit on the mat."},
            "tap": {"beginning": "t", "final": "p", "short_vowels": "a", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Tap the drum loudly."},

            #begning words
            "bat": {"beginning": "b", "final": "t", "short_vowels": "a", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "He hit the ball with a bat."},
            "fan": {"beginning": "f", "final": "n", "short_vowels": "a", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The fan keeps me cool."},
            "top": {"beginning": "t", "final": "p", "short_vowels": "o", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The top spins fast."},
            "pen": {"beginning": "p", "final": "n", "short_vowels": "e", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Write with a pen."},
            "bed": {"beginning": "b", "final": "d", "short_vowels": "e", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "I sleep in my bed."},
            "net": {"beginning": "n", "final": "t", "short_vowels": "e", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Catch fish in a net."},
            
            # Short i
            "sit": {"beginning": "s", "final": "t", "short_vowels": "i", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Sit on the chair."},
            "fin": {"beginning": "f", "final": "n", "short_vowels": "i", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The fish has a fin."},
            "pig": {"beginning": "p", "final": "g", "short_vowels": "i", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The pig is pink."},
            
            # Short o
            "pot": {"beginning": "p", "final": "t", "short_vowels": "o", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Cook soup in a pot."},
            "dog": {"beginning": "d", "final": "g", "short_vowels": "o", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The dog barks loudly."},
            "hop": {"beginning": "h", "final": "p", "short_vowels": "o", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The bunny can hop."},
            
            # Short u
            "cup": {"beginning": "c", "final": "p", "short_vowels": "u", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Drink from a cup."},
            "sun": {"beginning": "s", "final": "n", "short_vowels": "u", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The sun is bright."},
            "bug": {"beginning": "b", "final": "g", "short_vowels": "u", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "A bug crawled on the leaf."},
           
            #Ending words
            "cab": {"beginning": "c", "final": "b", "short_vowels": "a", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The cab stopped at the light."},
            "rug": {"beginning": "r", "final": "g", "short_vowels": "u", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The rug is soft."},
            "lip": {"beginning": "l", "final": "p", "short_vowels": "i", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "She put balm on her lip."},
            
        },
       "nonsense_words": {},
        "sight_words": {
            "to":   {"sentence": "I go to school."},
            "me":   {"sentence": "Give the ball to me."},
            "he":   {"sentence": "He runs very fast."},
            "see":  {"sentence": "I see a big dog."},
            "go":   {"sentence": "Let’s go to the park."},
            "no":   {"sentence": "No, I don’t want that."},
            "a":    {"sentence": "I have a red apple."},
            "it":   {"sentence": "Look at it!"},
            "in":   {"sentence": "The cat is in the box."},
            "on":   {"sentence": "The book is on the table."}
}
    },
    "First": {
        "regular_words": {
            "yet": {"beginning": "y", "final": "t", "short_vowels": "e", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "I haven't finished my homework yet."},
            "chap": {"beginning": "ch", "final": "p", "short_vowels": "a", "consonant_digraphs": "ch", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "The old book has a new chap."},
            "bed": {"beginning": "b", "final": "d", "short_vowels": "e", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "I sleep in a cozy bed."},
            "she": {"beginning": "sh", "final": "-", "short_vowels": "e", "consonant_digraphs": "sh", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "She runs very fast."},
            "ran": {"beginning": "r", "final": "n", "short_vowels": "a", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "He ran to catch the bus."},
            "hi": {"beginning": "h", "final": "-", "short_vowels": "i", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "i", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "She waved and said hi."},
            "go": {"beginning": "g", "final": "-", "short_vowels": "o", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "o", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Let's go to the park."},
            "quit": {"beginning": "qu", "final": "t", "short_vowels": "i", "consonant_digraphs": "-", "consonant_blends": "qu", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Don't quit the game now."},
            "cup": {"beginning": "c", "final": "p", "short_vowels": "u", "consonant_digraphs": "-", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "I drink from a red cup."},
            "with": {"beginning": "w", "final": "th", "short_vowels": "i", "consonant_digraphs": "th", "consonant_blends": "-", "long_vowel_patterns": "-", "other_vowel_patterns": "-", "inflected_endings": "-", "sentence": "Come with me to the store."}
        },
        "nonsense_words": {},
        "sight_words": {
            "is": {"sentence": "The cat is sleeping on the mat."},
            "the": {"sentence": "The dog chased the ball."},
            "my": {"sentence": "This is my favorite book."},
            "of": {"sentence": "She ate a piece of cake."},
            "and": {"sentence": "I like to read and write."},
        }
    },
    "Second": {
        "regular_words": {
            "quaint": {"beginning": "qu", "final": "nt", "short_vowel": "-", "digraph": "-", "blend": "nt", "long_vowel": "ai", "other_vowel": "-", "inflected": "-", "sentence": "The quaint village was peaceful."},
            "clunk": {"beginning": "cl", "final": "nk", "short_vowel": "u", "digraph": "-", "blend": "cl, nk", "long_vowel": "-", "other_vowel": "-", "inflected": "-", "sentence": "The old car made a clunk sound."},
            "coast": {"beginning": "c", "final": "st", "short_vowel": "-", "digraph": "-", "blend": "st", "long_vowel": "oa", "other_vowel": "-", "inflected": "-", "sentence": "We walked along the coast."},
            "standstill": {"beginning": "st", "final": "ll", "short_vowel": "a, i", "digraph": "-", "blend": "st, nd, st", "long_vowel": "-", "other_vowel": "-", "inflected": "-", "sentence": "Traffic came to a standstill."},
            "climax": {"beginning": "cl", "final": "x", "short_vowel": "i, a", "digraph": "-", "blend": "cl", "long_vowel": "-", "other_vowel": "-", "inflected": "-", "sentence": "The story reached its climax."},
            "bombastic": {"beginning": "b", "final": "c", "short_vowel": "o, a, i", "digraph": "-", "blend": "st", "long_vowel": "-", "other_vowel": "-", "inflected": "-", "sentence": "His speech was bombastic."},
            "strand": {"beginning": "str", "final": "nd", "short_vowel": "a", "digraph": "-", "blend": "str, nd", "long_vowel": "-", "other_vowel": "-", "inflected": "-", "sentence": "We found a strand of hair."},
            "graph": {"beginning": "gr", "final": "ph", "short_vowel": "a", "digraph": "ph", "blend": "gr", "long_vowel": "-", "other_vowel": "-", "inflected": "-", "sentence": "She drew a graph for class."},
            "hunted": {"beginning": "h", "final": "d", "short_vowel": "u, e", "digraph": "-", "blend": "nt", "long_vowel": "-", "other_vowel": "-", "inflected": "ed", "sentence": "They hunted for treasure."},
            "phone": {"beginning": "ph", "final": "n", "short_vowel": "-", "digraph": "ph", "blend": "-", "long_vowel": "o-e", "other_vowel": "-", "inflected": "-", "sentence": "She answered the phone."},
        },
        "nonsense_words": {},
        "sight_words": {
            "from": {"sentence": "I got a letter from my friend."},
            "does": {"sentence": "What does the sign say?"},
            "they": {"sentence": "They played soccer in the park."},
            "said": {"sentence": "She said hello to everyone."},
            "what": {"sentence": "What time is the party?"}
        }
    },
    "Third": {
        "regular_words": {
            "shower": {"beginning_consonant": "sh", "final_consonant": "r", "short_vowels": "o", "consonant_digraphs": "sh", "consonant_blends": "", "long_vowel_patterns": "", "other_vowel_patterns": "ow", "inflected_endings": "", "sentence": "The shower refreshed us after the hike."},
            "outline": {"beginning_consonant": "", "final_consonant": "n", "short_vowels": "", "consonant_digraphs": "", "consonant_blends": "", "long_vowel_patterns": "i-e", "other_vowel_patterns": "ou", "inflected_endings": "", "sentence": "She drew an outline of the map."},
            "candle": {"beginning_consonant": "c", "final_consonant": "l, e", "short_vowels": "a", "consonant_digraphs": "", "consonant_blends": "nd", "long_vowel_patterns": "", "other_vowel_patterns": "le", "inflected_endings": "", "sentence": "The candle lit the dark room."},
            "perplex": {"beginning_consonant": "p", "final_consonant": "x", "short_vowels": "e, e", "consonant_digraphs": "", "consonant_blends": "pr, pl", "long_vowel_patterns": "", "other_vowel_patterns": "", "inflected_endings": "", "sentence": "The puzzle began to perplex him."},
            "hamburger": {"beginning_consonant": "h", "final_consonant": "r", "short_vowels": "a, u, e", "consonant_digraphs": "", "consonant_blends": "mb, rg", "long_vowel_patterns": "", "other_vowel_patterns": "", "inflected_endings": "", "sentence": "We ate a juicy hamburger for lunch."},
            "turnstile": {"beginning_consonant": "t", "final_consonant": "l, e", "short_vowels": "u, i", "consonant_digraphs": "", "consonant_blends": "rn, st", "long_vowel_patterns": "", "other_vowel_patterns": "", "inflected_endings": "", "sentence": "He passed through the turnstile."},
            "amputate": {"beginning_consonant": "a (vowel start)", "final_consonant": "t, e", "short_vowels": "a, u", "consonant_digraphs": "", "consonant_blends": "mp, t", "long_vowel_patterns": "a-e", "other_vowel_patterns": "", "inflected_endings": "", "sentence": "The doctor had to amputate the leg."},
            "sixteen": {"beginning_consonant": "s", "final_consonant": "n", "short_vowels": "i, e", "consonant_digraphs": "", "consonant_blends": "xt", "long_vowel_patterns": "ee", "other_vowel_patterns": "", "inflected_endings": "", "sentence": "She turned sixteen last month."},
            "entertain": {"beginning_consonant": "e (vowel start)", "final_consonant": "n", "short_vowels": "e, a", "consonant_digraphs": "", "consonant_blends": "nt, rt", "long_vowel_patterns": "ai", "other_vowel_patterns": "", "inflected_endings": "", "sentence": "The clown will entertain the children."},
            "puzzle": {"beginning_consonant": "p", "final_consonant": "z, l, e", "short_vowels": "u", "consonant_digraphs": "zz", "consonant_blends": "", "long_vowel_patterns": "", "other_vowel_patterns": "le", "inflected_endings": "", "sentence": "The puzzle took hours to solve."},
        },
        "nonsense_words": {},
        "sight_words": {
            "there": {"sentence": "There is a bird in the tree."},
            "which": {"sentence": "Which book do you like best?"},
            "although": {"sentence": "Although it was raining, we went outside."},
            "people": {"sentence": "Many people came to the party."},
            "could": {"sentence": "I could hear the music from far away."}
        }
    }
}

# Helper: pick exactly 10 UNIQUE Kindergarten regular words
def _select_kindergarten_regular_words() -> List[Dict]:
    all_words = [(w, data) for w, data in word_lists["Kindergarten"]["regular_words"].items()]
    by_vowel = {v: [] for v in "aeiou"}
    for w, data in all_words:
        short_v = data.get("short_vowels", "-")
        if short_v in by_vowel:
            by_vowel[short_v].append((w, data))

    selected_words = []
    used_words = set()

    # One per vowel
    for vowel in "aeiou":
        for w, data in by_vowel[vowel]:
            if w not in used_words:
                selected_words.append({"word": w, "sentence": data["sentence"], "type": "regular"})
                used_words.add(w)
                break

    # Two beginning, two ending
    for _ in range(2):
        for w, d in all_words:
            if w not in used_words and d.get("beginning") != "-":
                selected_words.append({"word": w, "sentence": d["sentence"], "type": "regular"})
                used_words.add(w)
                break
    for _ in range(2):
        for w, d in all_words:
            if w not in used_words and d.get("final") != "-":
                selected_words.append({"word": w, "sentence": d["sentence"], "type": "regular"})
                used_words.add(w)
                break

    # Fill to 10
    remaining = [(w, d) for w, d in all_words if w not in used_words]
    random.shuffle(remaining)
    needed = 10 - len(selected_words)
    for w, d in remaining[:needed]:
        selected_words.append({"word": w, "sentence": d["sentence"], "type": "regular"})
        used_words.add(w)

    assert len(selected_words) == 10
    return selected_words

def _audio_words_for_grade(grade: str) -> List[Dict]:
    words = []
    if grade == "Kindergarten":
        for item in _select_kindergarten_regular_words():
            words.append({"word": item["word"], "type": "regular", "sentence": item["sentence"]})
    else:
        for w, data in word_lists[grade].get("regular_words", {}).items():
            if "sentence" in data:
                words.append({"word": w, "type": "regular", "sentence": data["sentence"]})
    for w, data in word_lists[grade].get("sight_words", {}).items():
        if "sentence" in data:
            words.append({"word": w, "type": "sight", "sentence": data["sentence"]})
    return words

# Scoring per word (unchanged)
def score_response(word: str, user_input: str, grade: str, word_type: str) -> Dict:
    user_input = user_input.strip().lower()
    word_lower = word.lower()

    # EXACT SPELLING = FULL POINTS
    if user_input == word_lower and word_type == "regular":
        word_data = word_lists[grade]["regular_words"][word_lower]
        max_points = sum(1 for k, v in word_data.items() 
                        if k != "sentence" and str(v).strip() not in ["", "-", " "])
        return {"points": max_points, "max_points": max_points, "mistakes": {}}

    # SIGHT / NONSENSE: 1 point only
    if word_type in ["sight", "nonsense"]:
        return {
            "points": 1 if user_input == word_lower else 0,
            "max_points": 1,
            "mistakes": {"spelling": f"Expected '{word}', got '{user_input}'"} if user_input != word_lower else {}
        }

    # REGULAR WORD: SCORE FEATURES
    word_data = word_lists[grade]["regular_words"].get(word_lower, {})
    if not word_data:
        return {"points": 0, "max_points": 0, "mistakes": {"invalid": "Word not in list"}}

    points = 0
    mistakes = {}
    feature_list = {
        "Kindergarten": ["beginning", "final", "short_vowels", "consonant_digraphs", "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"],
        "First": ["beginning", "final", "short_vowel", "digraph", "blend", "long_vowel", "other_vowel", "inflected"],
        "Second": ["beginning_consonant", "final_consonant", "short_vowels", "consonant_digraphs", "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"],
        "Third": ["beginning_consonant", "final_consonant", "short_vowels", "consonant_digraphs", "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"]
    }.get(grade, [])

    for feature in feature_list:
        val = str(word_data.get(feature, "")).strip()
        if not val or val in ["-", ""]: 
            continue
        clean_val = "".join(c for c in val.lower() if c.isalpha())

        if feature in ["beginning", "beginning_consonant"]:
            if user_input.startswith(clean_val):
                points += 1
            else:
                mistakes[feature] = val
        elif feature in ["final", "final_consonant"]:
            if user_input.endswith(clean_val):
                points += 1
            else:
                mistakes[feature] = val
        elif feature in ["long_vowel", "long_vowel_patterns"] and "-" in val:
            v, _, e = val.partition("-")
            if v.lower() in user_input and e.lower() in user_input:
                points += 1
            else:
                mistakes[feature] = val
        elif any(p in user_input for p in [p.strip().lower() for p in val.split(",") if p.strip()]):
            points += 1
        else:
            mistakes[feature] = val

    max_points = sum(1 for f in feature_list if str(word_data.get(f, "")).strip() not in ["", "-", " "])
    return {"points": points, "max_points": max_points, "mistakes": mistakes}

# NEW: evaluate_test uses TOTAL POINTS (real score)
def evaluate_test(results: List[Dict], grade: str) -> Dict:
    total_points   = sum(r["points"] for r in results)
    max_points     = sum(r["max_points"] for r in results)
    word_count     = len(results)
    correct_count  = sum(1 for r in results if r["points"] == r["max_points"])

    if max_points == 0:
        status = "Below"
    else:
        pct = total_points / max_points
        status = "Above" if pct >= 0.90 else ("At" if pct >= 0.70 else "Below")

    return {
        "status": status,
        "score": total_points,
        "max_score": max_points,
        "words_tested": word_count,
        "correct_count": correct_count
    }

def analyze_errors(results: List[Dict], grade: str) -> Dict:
    feature_mapping = {
        "Kindergarten": ["beginning", "final", "short_vowels", "consonant_digraphs", "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"],
        "First": ["beginning", "final", "short_vowel", "digraph", "blend", "long_vowel", "other_vowel", "inflected"],
        "Second": ["beginning_consonant", "final_consonant", "short_vowels", "consonant_digraphs", "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"],
        "Third": ["beginning_consonant", "final_consonant", "short_vowels", "consonant_digraphs", "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"]
    }
    
    error_counts = {
        "Beginning consonant error": 0,
        "Ending consonant error": 0,
        "Short vowel error": 0,
        "Consonant digraph error": 0,
        "Consonant blend error": 0,
        "Long vowel pattern error": 0,
        "Other vowel pattern error": 0,
        "Inflected ending error": 0
    }
    
    feature_to_error = {
        "beginning": "Beginning consonant error",
        "beginning_consonant": "Beginning consonant error",
        "final": "Ending consonant error",
        "final_consonant": "Ending consonant error",
        "short_vowel": "Short vowel error",
        "short_vowels": "Short vowel error",
        "digraph": "Consonant digraph error",
        "consonant_digraphs": "Consonant digraph error",
        "blend": "Consonant blend error",
        "consonant_blends": "Consonant blend error",
        "long_vowel": "Long vowel pattern error",
        "long_vowel_patterns": "Long vowel pattern error",
        "other_vowel": "Other vowel pattern error",
        "other_vowel_patterns": "Other vowel pattern error",
        "inflected": "Inflected ending error",
        "inflected_endings": "Inflected ending error"
    }
    
    for result in results:
        if result.get("type") == "regular" and result.get("mistakes"):
            mistakes = result.get("mistakes", {})
            for feature in mistakes:
                if feature in feature_to_error:
                    error_counts[feature_to_error[feature]] += 1
    
    return error_counts

def get_recommendation(error_counts: Dict, status: str, results: List[Dict], grade: str) -> str:
    if status == "Above":
        return f"Advance to next level. Continue practicing all phonics patterns."
    areas = [k.replace(" error", "") for k, v in error_counts.items() if v > 0]
    if areas:
        beginning_errors = [r for r in results if r.get("type") == "regular" and ("beginning" in r.get("mistakes", {}) or "beginning_consonant" in r.get("mistakes", {}))]
        if beginning_errors:
            first_mistake_word = beginning_errors[0]["word"]
            word_data = word_lists[grade]["regular_words"].get(first_mistake_word, {})
            start_letter = word_data.get("beginning", word_data.get("beginning_consonant", "A")).split(",")[0][0].upper()
            return f"Begin at letter {start_letter} in the phonics progression. Continue practicing: {', '.join(areas)}."
        return f"Continue practicing: {', '.join(areas)}."
    return "Continue practicing all phonics patterns."

# Firebase Authentication Dependency
security = HTTPBearer(auto_error=False)

async def get_firebase_user(token: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        decoded_token = auth.verify_id_token(token.credentials)
        return decoded_token
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Endpoints
@app.post("/grade/")
async def submit_test(grade_input: GradeInput):
    grade = grade_input.grade
    if grade not in ["Kindergarten", "First", "Second", "Third"]:
        raise HTTPException(status_code=400, detail="Invalid grade")
    
    words_to_test = []

    if grade == "Kindergarten":
        regular = _select_kindergarten_regular_words()
    else:
        regular = [
            {"word": word, "sentence": data["sentence"], "type": "regular"}
            for word, data in word_lists[grade]["regular_words"].items()
        ]

    nonsense_dict = word_lists[grade].get("nonsense_words", {})
    nonsense = [
        {"word": word, "sentence": data["sentence"], "type": "nonsense"}
        for word, data in nonsense_dict.items()
    ]

    sight_dict = word_lists[grade].get("sight_words", {})
    sight = [
        {"word": word, "sentence": data["sentence"], "type": "sight"}
        for word, data in sight_dict.items()
    ]

    words_to_test = regular + nonsense + sight
    return {"words": words_to_test}

@app.post("/register/")
async def register_user(user: UserCreate):
    try:
        firebase_user = auth.create_user(
            email=user.email,
            password=user.password,
            display_name=user.name
        )
        db_ref.child(f"users/{firebase_user.uid}").set({
            "name": user.name,
            "email": user.email,
        })
        return {"message": "User created successfully", "user_id": firebase_user.uid}
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/login")
async def login_user(user: UserLogin):
    try:
        response = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
            json={
                "email": user.email,
                "password": user.password,
                "returnSecureToken": True
            }
        )
        response_data = response.json()
        if response.status_code == 200 and "idToken" in response_data:
            return {
                "id_token": response_data["idToken"],
                "refresh_token": response_data["refreshToken"],
                "expires_in": response_data["expiresIn"],
                "user_id": response_data["localId"]
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Login failed: {response_data.get('error', {}).get('message', 'Unknown error')}"
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Login failed: {str(e)}")

@app.post("/save-user-data/")
async def save_user_data(user_data: UserCreate):
    try:
        decoded_token = auth.verify_id_token(user_data.idToken)
        user_id = decoded_token["uid"]
        data_to_save = {
            "name": user_data.name,
            "email": user_data.email,
            "created_at": datetime.utcnow().isoformat()
        }
        db_ref.child(f"users/{user_id}").set(data_to_save)
        return {"message": "User data saved successfully", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save user data: {str(e)}")

@app.post("/user-details/")
async def get_user_details(user_details: UserDetails):
    try:
        decoded_token = auth.verify_id_token(user_details.idToken)
        user_id = decoded_token["uid"]
        user_data = db_ref.child(f"users/{user_id}").get()
        if user_data:
            if (user_data.get("email") == user_details.email and
                user_data.get("name") == user_details.name and
                user_data.get("age") == user_details.age):
                return {
                    "name": user_data.get("name", ""),
                    "email": user_data.get("email", ""),
                    "age": user_data.get("age", "")
                }
            else:
                raise HTTPException(status_code=400, detail="Provided user details do not match stored data")
        else:
            raise HTTPException(status_code=404, detail="User data not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user details: {str(e)}")

@app.post("/add_child/")
async def add_child(child: ChildCreate):
    try:
        decoded_token = auth.verify_id_token(child.idToken)
        user_id = decoded_token["uid"]
        child_id = str(uuid.uuid4())
        if not child.name or child.age < 0 or child.grade not in ["Kindergarten", "First", "Second", "Third"]:
            raise HTTPException(status_code=400, detail="Invalid child data: name, age, or grade")
        child_data = {
            "name": child.name,
            "age": child.age,
            "grade": child.grade,
            "created_at": datetime.utcnow().isoformat()
        }
        db_ref.child(f"users/{user_id}/children/{child_id}").set(child_data)
        return {"child_id": child_id, "message": "Child added successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add child: {str(e)}")

@app.post("/get_children/")
async def get_children(request: GetDetailsRequest):
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
        children_data = db_ref.child(f"users/{user_id}/children").get() or {}
        children = [
            ChildDetails(
                child_id=child_id,
                name=data.get("name", ""),
                age=data.get("age", 0),
                grade=data.get("grade", "")
            )
            for child_id, data in children_data.items()
        ]
        return {"children": children}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch children: {str(e)}")

def sanitize_firebase_key(key: str) -> str:
    invalid_chars = ['.', '#', '$', '[', ']', '/']
    sanitized = key
    for char in invalid_chars:
        sanitized = sanitized.replace(char, '_')
    return sanitized

def sanitize_firebase_data(data):
    if isinstance(data, dict):
        return {sanitize_firebase_key(k): sanitize_firebase_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_firebase_data(item) for item in data]
    elif isinstance(data, (set, tuple)):
        return [sanitize_firebase_data(item) for item in list(data)]
    elif isinstance(data, (datetime,)):
        return data.isoformat()
    elif isinstance(data, (int, float, str, bool)) or data is None:
        return data
    else:
        return str(data)

@app.post("/get_all_child_details/")
async def get_all_child_details(request: GetDetailsRequest):
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
        children_data = db_ref.child(f"users/{user_id}/children").get() or {}
        children = []
        for child_id, data in children_data.items():
            scores_data = db_ref.child(f"users/{user_id}/children/{child_id}/scores").get() or {}
            scores = [
                {
                    "score_id": score_id,
                    "grade": score_data.get("grade", ""),
                    "evaluation": score_data.get("evaluation", {}),
                    "assessment_summary": score_data.get("assessment_summary", {}),
                    "error_analysis": score_data.get("error_analysis", {}),
                    "instructional_recommendation": score_data.get("instructional_recommendation", ""),
                    "timestamp": score_data.get("timestamp", "")
                }
                for score_id, score_data in scores_data.items()
            ]
            children.append(
                ChildDetailsWithScores(
                    child_id=child_id,
                    name=data.get("name", ""),
                    age=data.get("age", 0),
                    grade=data.get("grade", ""),
                    scores=scores
                )
            )
        return {"children": children}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch detailed children data: {str(e)}")

@app.post("/submit_words/")
async def submit_words(request: SubmitWordsRequest):
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")

    grade = request.grade
    if grade not in word_lists:
        raise HTTPException(status_code=400, detail="Invalid grade")

    results = []
    analysis = []
    for word_data in request.words:
        word = word_data.word
        user_input = word_data.user_input
        word_type = word_data.type
        time = word_data.time
        hints_used = word_data.hints_used
        if word_type in ["sight", "nonsense"]:
            score = score_response(word, user_input, grade, word_type)
            results.append({"word": word, "user_input": user_input, "type": word_type, "time": time, "hints_used": hints_used, **score})
            analysis.append({
                "word": word,
                "user_input": user_input,
                "explanation": score["mistakes"].get("spelling", f"Correct {word_type} word.")
            })
        elif word_type == "regular" and word in word_lists[grade]["regular_words"]:
            score = score_response(word, user_input, grade, word_type)
            results.append({"word": word, "user_input": user_input, "type": word_type, "time": time, "hints_used": hints_used, **score})
            analysis_entry = {"word": word, "user_input": user_input}
            for feature in word_lists[grade]["regular_words"][word].keys():
                if feature == "sentence" or word_lists[grade]["regular_words"][word][feature] in ["-", ""]:
                    continue
                sanitized_feature = sanitize_firebase_key(feature)
                user_value = user_input[:len(word_lists[grade]["regular_words"][word][feature].split(",")[-1])] if feature in ["beginning", "final", "beginning_consonant", "final_consonant"] else user_input
                if feature in score["mistakes"]:
                    analysis_entry[f"{sanitized_feature}_explanation"] = f"Mistake in {feature}: Expected '{word_lists[grade]['regular_words'][word][feature]}', got '{user_value}'."
                else:
                    analysis_entry[f"{sanitized_feature}_explanation"] = f"Correct {feature}: Matched '{word_lists[grade]['regular_words'][word][feature]}'."
            analysis.append(analysis_entry)
        else:
            results.append({"word": word, "user_input": user_input, "points": 0, "max_points": 0, "mistakes": {"invalid": "Word not in list"}, "type": word_type, "time": time, "hints_used": hints_used})
            analysis.append({"word": word, "user_input": user_input, "invalid_explanation": f"'{word}' is not a valid word in the list."})

    evaluation = evaluate_test(results, grade)
    error_counts = analyze_errors([r for r in results if r["type"] == "regular"], grade)
    recommendation = get_recommendation(error_counts, evaluation["status"], results, grade)

    phonics = [r for r in results if r["type"] == "regular"]
    sight = [r for r in results if r["type"] == "sight"]
    assessment_summary = {
        "Phonics": {
            "score": sum(r["points"] for r in phonics),
            "max_score": sum(r["max_points"] for r in phonics),
            "percentage": round(sum(r["points"] for r in phonics) / sum(r["max_points"] for r in phonics) * 100, 1) if phonics else 0
        },
        "Sight Words": {
            "score": sum(r["points"] for r in sight),
            "max_score": sum(r["max_points"] for r in sight),
            "percentage": round(sum(r["points"] for r in sight) / sum(r["max_points"] for r in sight) * 100, 1) if sight else 0
        }
    }

    score_id = db_ref.child(f"users/{user_id}/children/{request.child_id}/scores").push().key
    score_data = {
        "grade": grade,
        "evaluation": evaluation,
        "assessment_summary": sanitize_firebase_data(assessment_summary),
        "error_analysis": sanitize_firebase_data(error_counts),
        "instructional_recommendation": recommendation,
        "results": sanitize_firebase_data(results),
        "analysis": sanitize_firebase_data(analysis),
        "timestamp": datetime.utcnow().isoformat()
    }
    db_ref.child(f"users/{user_id}/children/{request.child_id}/scores/{score_id}").set(score_data)

    return {
        "user_id": user_id,
        "child_id": request.child_id,
        "results": results,
        "analysis": analysis,
        "evaluation": evaluation,
        "assessment_summary": assessment_summary,
        "error_analysis": error_counts,
        "instructional_recommendation": recommendation
    }

@app.post("/generate_text_audio/")
async def generate_word_audio(request: AudioRequest):
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token['uid']
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    word = request.text
    try:
        word_response = polly_client.synthesize_speech(
            Text=word,
            OutputFormat='mp3',
            VoiceId='Joanna'
        )
        word_audio = word_response['AudioStream'].read()
        word_base64 = base64.b64encode(word_audio).decode('utf-8')
        return {"base64_audio": word_base64}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate audio: {str(e)}")

@app.post("/generate_all_grade_audio/")
async def generate_all_grade_audio(request: GradeInput):
    grade = request.grade
    if grade not in word_lists:
        raise HTTPException(status_code=400, detail="Invalid grade")

    words = _audio_words_for_grade(grade)
    if not words:
        raise HTTPException(status_code=404, detail="No words with sentences found")

    audio_files = []
    try:
        for item in words:
            word = item["word"]
            sentence = item["sentence"]
            word_type = item["type"]

            word_ssml = f'<speak><prosody rate="95%">{word}</prosody></speak>'
            word_response = polly_client.synthesize_speech(
                Text=word_ssml,
                TextType='ssml',
                OutputFormat='mp3',
                VoiceId='Joanna'
            )
            word_audio = word_response['AudioStream'].read()

            sentence_ssml = f'<speak><prosody rate="95%">{sentence}</prosody></speak>'
            sentence_response = polly_client.synthesize_speech(
                Text=sentence_ssml,
                TextType='ssml',
                OutputFormat='mp3',
                VoiceId='Joanna'
            )
            sentence_audio = sentence_response['AudioStream'].read()

            word_base64 = base64.b64encode(word_audio).decode('utf-8')
            sentence_base64 = base64.b64encode(sentence_audio).decode('utf-8')

            audio_files.append({
                "word": word,
                "word_type": word_type,
                "word_audio": word_base64,
                "sentence_audio": sentence_base64,
                "word_filename": f"{word_type}/{word}_word.mp3",
                "sentence_filename": f"{word_type}/{word}_sentence.mp3"
            })
        
        return {"grade": grade, "audio_files": audio_files}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate audio: {str(e)}")

@app.delete("/delete_child/")
async def delete_child(request: DeleteChildRequest):
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    child_ref = db_ref.child(f"users/{user_id}/children/{request.child_id}")
    child_snapshot = child_ref.get()

    if not child_snapshot:
        raise HTTPException(status_code=404, detail="Child not found")

    try:
        scores_ref = db_ref.child(f"users/{user_id}/children/{request.child_id}/scores")
        scores_ref.delete()
        child_ref.delete()
        return {"message": "Child and all associated data deleted successfully.", "deleted_child_id": request.child_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete child: {str(e)}")

@app.post("/complete_result/")
async def complete_result(request: CompleteResultRequest):
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")

    requested_grade = request.grade  # Optional: "First", "Third", etc.
    allowed_grades = ["Kindergarten", "First", "Second", "Third"]

    # Fetch ALL scores
    scores_data = db_ref.child(f"users/{user_id}/children/{request.child_id}/scores").get() or {}
    if not scores_data:
        raise HTTPException(status_code=404, detail="No test results found")

    # Filter by requested grade (if provided)
    filtered_scores = []
    for score_id, score_data in scores_data.items():
        grade = score_data.get("grade")
        if grade not in allowed_grades:
            continue
        if requested_grade and grade != requested_grade:
            continue
        filtered_scores.append((score_data.get("timestamp", ""), score_data, grade))

    if not filtered_scores:
        raise HTTPException(status_code=404, detail=f"No results found for grade: {requested_grade or 'any'}")

    # Sort by timestamp (newest first)
    filtered_scores.sort(key=lambda x: x[0], reverse=True)
    latest_timestamp, latest_data, result_grade = filtered_scores[0]
    all_results = latest_data.get("results", [])

    # === Build Summary for the SELECTED result ===
    total_words = len(all_results)
    correct_count = sum(1 for r in all_results if r["points"] == r["max_points"])
    overall_accuracy = (correct_count / total_words * 100) if total_words > 0 else 0

    phonics = [r for r in all_results if r["type"] == "regular"]
    sight = [r for r in all_results if r["type"] == "sight"]
    phonics_score = (sum(r["points"] for r in phonics) / sum(r["max_points"] for r in phonics) * 100) if phonics and sum(r["max_points"] for r in phonics) > 0 else 0
    sight_word_score = (sum(r["points"] for r in sight) / sum(r["max_points"] for r in sight) * 100) if sight and sum(r["max_points"] for r in sight) > 0 else 0

    score_variance = abs(phonics_score - sight_word_score) if phonics and sight else 0
    average_score = (phonics_score + sight_word_score) / 2 if phonics and sight else overall_accuracy
    confidence = ("High" if score_variance < 20 and average_score > 70 else
                  "Medium" if score_variance < 20 and average_score > 40 else "Low")

    evaluation = evaluate_test(all_results, result_grade)
    error_counts = analyze_errors(phonics, result_grade)
    key_error_patterns = [{"pattern": k.replace(" error", ""), "count": v} for k, v in error_counts.items() if v > 0]
    strengths = [k.replace(" error", "") for k, v in error_counts.items() if v == 0 or v < 2]
    focus_areas = [k.replace(" error", "") for k, v in error_counts.items() if v >= 2]
    recommendation = get_recommendation(error_counts, evaluation["status"], all_results, result_grade)

    # Placement & Next Step
    if evaluation["status"] == "Above":
        placement = "Above Grade Level"
        next_step = "Unlock Next Test" if result_grade == "Third" else "Unlock Next Grade"
    elif evaluation["status"] == "At":
        placement = "At Grade Level"
        next_step = "Continue current grade"
    else:
        placement = "Below Grade Level"
        next_step = "Continue current grade"

    grade_band = "K-3rd" if result_grade in ["Kindergarten", "First", "Second", "Third"] else result_grade

    table_data = [
        {
            "word": r["word"],
            "attempt": r["user_input"],
            "correct": r["points"] == r["max_points"],
            "error_type": next((k for k, v in r.get("mistakes", {}).items() if k != "spelling"), None) or ("Sight word" if r["type"] == "sight" and not r["points"] else None),
            "time": r.get("time", 0.0),
            "hints_used": r.get("hints_used", 0),
            "icon": "Correct" if r["points"] == r["max_points"] else "Incorrect"
        }
        for r in all_results
    ]

    return {
        "user_id": user_id,
        "child_id": request.child_id,
        "grade": result_grade,
        "parent_summary": {
            "overall_accuracy": round(overall_accuracy),
            "phonics_score": round(phonics_score),
            "sight_word_score": round(sight_word_score),
            "confidence": confidence,
            "key_error_patterns": key_error_patterns,
            "recommendation": recommendation,
            "note": "Note: Placement is instructional and not a clinical diagnosis.",
            "strengths": strengths,
            "focus_areas": focus_areas,
            "grade_band": {
                "band": grade_band,
                "placement": placement,
                "next_step": next_step
            },
            "actions": [
                {"label": "Start Practice Pack", "type": "button", "action": "start_pack"},
                {"label": "Review Missed Words", "type": "button", "action": "review_missed"},
                {"label": "Download Report (PDF)", "type": "button", "action": "download_pdf"}
            ]
        },
        "teacher_admin_detail": {
            "test_level": result_grade,
            "words": total_words,
            "correct": correct_count,
            "instructional_level": result_grade,
            "table_data": table_data,
            "actions": [
                {"label": "Export CSV", "type": "button", "action": "export_csv"},
                {"label": "Copy JSON", "type": "button", "action": "copy_json"},
                {"label": "Send to Tutor", "type": "button", "action": "send_tutor"}
            ]
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)