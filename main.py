from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import firebase_admin
import openai
import tempfile
import re
import io

from firebase_admin import auth as firebase_auth
from dotenv import load_dotenv
from firebase_admin import credentials, auth, db
import requests
import uuid
import os
import time
import base64
import json
from typing import Optional
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

# OpenAI API Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

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

class FeedbackRequest(BaseModel):
    idToken: str
    child_id: str

    # Answers from frontend
    q1_grade: str
    q2_prior_assessments: str
    q3_spelling_confidence: str
    q4_assessment_length: str
    q5_difficulty_level: str
    q6_engagement_level: str
    q7_technical_issues: str
    q8_results_clarity: str
    q9_recommendations_helpful: str
    q10_information_amount: str
    q11_overall_satisfaction: str
    q12_comments: Optional[str] = ""

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
class MakeAdminRequest(BaseModel):
    idToken: str
    targetEmail: str  # email instead of UID

# ==================== SPEAKING TEST MODELS ====================
class SpeakingSentenceRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str

class SpeakingAnalyzeRequest(BaseModel):
    """Request to analyze speech from base64 audio"""
    idToken: str
    child_id: str
    grade: str
    original_sentence: str
    audio_base64: str  # Base64 encoded audio (mp3, wav, webm, m4a)
    audio_format: str = "mp3"  # Format hint: mp3, wav, webm, m4a

class SpeakingSubmissionItem(BaseModel):
    """Single submission item for batch processing"""
    sentence_id: str
    original_sentence: str
    audio_base64: str
    audio_format: str = "mp3"

class SpeakingSubmitRequest(BaseModel):
    """Submit speaking test - supports single or batch submission"""
    idToken: str
    child_id: str
    grade: str
    # Single submission (backward compatible)
    sentence_id: Optional[str] = None
    original_sentence: Optional[str] = None
    audio_base64: Optional[str] = None
    audio_format: Optional[str] = "mp3"
    # Batch submission
    submissions: Optional[List[SpeakingSubmissionItem]] = None

class SpeakingResultRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str = None

# ==================== SPEAKING TEST SENTENCE LISTS ====================
speaking_sentences = {
    "Kindergarten": [
        {"id": "k1", "sentence": "The cat sat on the mat.", "word_count": 6, "difficulty": "easy"},
        {"id": "k2", "sentence": "I see a big red dog.", "word_count": 6, "difficulty": "easy"},
        {"id": "k3", "sentence": "The sun is very hot.", "word_count": 5, "difficulty": "easy"},
        {"id": "k4", "sentence": "My mom has a blue cup.", "word_count": 6, "difficulty": "easy"},
        {"id": "k5", "sentence": "The fish can swim fast.", "word_count": 5, "difficulty": "easy"},
        {"id": "k6", "sentence": "I like to run and hop.", "word_count": 6, "difficulty": "medium"},
        {"id": "k7", "sentence": "The little bug is on the leaf.", "word_count": 7, "difficulty": "medium"},
        {"id": "k8", "sentence": "Dad and I play in the park.", "word_count": 7, "difficulty": "medium"},
    ],
    "First": [
        {"id": "f1", "sentence": "The brown dog likes to play with the ball.", "word_count": 9, "difficulty": "easy"},
        {"id": "f2", "sentence": "She went to the store to buy some apples.", "word_count": 9, "difficulty": "easy"},
        {"id": "f3", "sentence": "The children are playing outside in the rain.", "word_count": 8, "difficulty": "medium"},
        {"id": "f4", "sentence": "My friend has a pretty yellow flower.", "word_count": 7, "difficulty": "easy"},
        {"id": "f5", "sentence": "We like to read books before bedtime.", "word_count": 7, "difficulty": "medium"},
        {"id": "f6", "sentence": "The rabbit jumped over the small fence.", "word_count": 7, "difficulty": "medium"},
        {"id": "f7", "sentence": "I can see the bright stars at night.", "word_count": 8, "difficulty": "medium"},
        {"id": "f8", "sentence": "The teacher told us a funny story today.", "word_count": 8, "difficulty": "medium"},
    ],
    "Second": [
        {"id": "s1", "sentence": "The beautiful butterfly landed on the colorful flower.", "word_count": 8, "difficulty": "medium"},
        {"id": "s2", "sentence": "Yesterday we went to the zoo and saw elephants.", "word_count": 9, "difficulty": "medium"},
        {"id": "s3", "sentence": "My grandmother bakes delicious cookies every weekend.", "word_count": 7, "difficulty": "medium"},
        {"id": "s4", "sentence": "The excited children ran quickly to the playground.", "word_count": 8, "difficulty": "medium"},
        {"id": "s5", "sentence": "We learned about different animals in science class.", "word_count": 8, "difficulty": "hard"},
        {"id": "s6", "sentence": "The thunder was loud but the lightning was bright.", "word_count": 9, "difficulty": "hard"},
        {"id": "s7", "sentence": "She carefully placed the fragile glass on the table.", "word_count": 9, "difficulty": "hard"},
        {"id": "s8", "sentence": "The astronaut floated in space looking at Earth.", "word_count": 8, "difficulty": "hard"},
    ],
    "Third": [
        {"id": "t1", "sentence": "The magnificent castle stood proudly on top of the mountain.", "word_count": 10, "difficulty": "medium"},
        {"id": "t2", "sentence": "Scientists discovered an unusual species of fish in the ocean.", "word_count": 10, "difficulty": "hard"},
        {"id": "t3", "sentence": "The determined athlete practiced every morning before school started.", "word_count": 8, "difficulty": "hard"},
        {"id": "t4", "sentence": "My favorite subject is mathematics because I enjoy solving problems.", "word_count": 9, "difficulty": "hard"},
        {"id": "t5", "sentence": "The ancient Egyptian pyramids are thousands of years old.", "word_count": 8, "difficulty": "hard"},
        {"id": "t6", "sentence": "We celebrated my sister's birthday with a spectacular surprise party.", "word_count": 9, "difficulty": "hard"},
        {"id": "t7", "sentence": "The courageous firefighter rescued the kitten from the tall tree.", "word_count": 10, "difficulty": "hard"},
        {"id": "t8", "sentence": "Reading comprehension improves when you practice regularly every day.", "word_count": 8, "difficulty": "hard"},
    ]
}

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

import random
import base64
from fastapi import HTTPException

# ----------------------------------------------------------------------
# HUMAN-LIKE VOICE SETTINGS
# ----------------------------------------------------------------------
NEURAL_VOICE_ID = "Joanna"        # American female – warm, clear, child-friendly
LANGUAGE_CODE   = "en-US"         # American English

@app.post("/generate_all_grade_audio/")
async def generate_all_grade_audio(request: GradeInput):
    grade = request.grade
    if grade not in word_lists:
        raise HTTPException(status_code=400, detail="Invalid grade")

    # === GET WORDS ===
    words = _audio_words_for_grade(grade)
    if not words:
        raise HTTPException(status_code=404, detail="No words with sentences found")

    # === SHUFFLE EVERY TIME (NEW!) ===
    shuffled_words = words.copy()
    random.shuffle(shuffled_words)

    audio_files = []

    try:
        for item in shuffled_words:
            word = item["word"]
            sentence = item["sentence"]
            word_type = item["type"]

            # === SSML: Word (slow) + Sentence (normal) ===
            word_ssml = f'<speak><prosody rate="95%">{word}</prosody></speak>'
            sentence_ssml = f'<speak><prosody rate="100%">{sentence}</prosody></speak>'

            # === WORD AUDIO (Neural HD) ===
            word_response = polly_client.synthesize_speech(
                Text=word_ssml,
                TextType='ssml',
                OutputFormat='mp3',
                VoiceId=NEURAL_VOICE_ID,
                Engine='neural',           # HD, human-like
                LanguageCode=LANGUAGE_CODE
            )
            word_audio = word_response['AudioStream'].read()

            # === SENTENCE AUDIO (Neural HD) ===
            sentence_response = polly_client.synthesize_speech(
                Text=sentence_ssml,
                TextType='ssml',
                OutputFormat='mp3',
                VoiceId=NEURAL_VOICE_ID,
                Engine='neural',
                LanguageCode=LANGUAGE_CODE
            )
            sentence_audio = sentence_response['AudioStream'].read()

            # === BASE64 ENCODE (EXACT SAME AS BEFORE) ===
            word_base64 = base64.b64encode(word_audio).decode('utf-8')
            sentence_base64 = base64.b64encode(sentence_audio).decode('utf-8')

            # === SAME JSON STRUCTURE (100% compatible) ===
            audio_files.append({
                "word": word,
                "word_type": word_type,
                "word_audio": word_base64,
                "sentence_audio": sentence_base64,
                "word_filename": f"{word_type}/{word}_word.mp3",
                "sentence_filename": f"{word_type}/{word}_sentence.mp3"
            })

        return {
            "grade": grade,
            "audio_files": audio_files  # SHUFFLED + HD AUDIO
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate audio: {str(e)}"
        )

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

    requested_grade = request.grade
    allowed_grades = ["Kindergarten", "First", "Second", "Third"]

    # === Fetch & Filter Scores ===
    scores_data = db_ref.child(f"users/{user_id}/children/{request.child_id}/scores").get() or {}
    if not scores_data:
        raise HTTPException(status_code=404, detail="No test results found")

    filtered = []
    for score_id, s in scores_data.items():
        g = s.get("grade")
        if g not in allowed_grades or (requested_grade and g != requested_grade):
            continue
        filtered.append((s.get("timestamp", ""), s, g))

    if not filtered:
        raise HTTPException(status_code=404, detail=f"No results for grade: {requested_grade or 'any'}")

    filtered.sort(key=lambda x: x[0], reverse=True)
    _, latest, result_grade = filtered[0]
    all_results = latest.get("results", [])

    phonics = [r for r in all_results if r["type"] == "regular"]
    sight   = [r for r in all_results if r["type"] == "sight"]

    # === No Phonics Attempted ===
    if not phonics:
        return {
            "user_id": user_id,
            "child_id": request.child_id,
            "grade": result_grade,
            "parent_summary": {
                "overall_accuracy": 0,
                "phonics_score": 0,
                "sight_word_score": round((sum(r["points"] for r in sight) / sum(r["max_points"] for r in sight) * 100), 1) if sight else 0,
                "confidence": "Low",
                "key_error_patterns": [],
                "strengths": [],
                "focus_areas": [],
                "recommendation": "No phonics words attempted. Start with basic letter sounds.",
                "note": "Note: Placement is instructional and not a clinical diagnosis.",
                "grade_band": {"band": result_grade, "placement": "Below Grade Level", "next_step": "Begin phonics practice"},
                "actions": [
                    {"label": "Start Practice Pack", "type": "button", "action": "start_pack"},
                    {"label": "Review Missed Words", "type": "button", "action": "review_missed"},
                    {"label": "Download Report (PDF)", "type": "button", "action": "download_pdf"}]
            },
            "teacher_admin_detail": {
                "test_level": result_grade,
                "words": len(all_results),
                "correct": sum(1 for r in all_results if r["points"] == r["max_points"]),
                "instructional_level": result_grade,
                "table_data": [],
                "actions": [
                    {"label": "Export CSV", "type": "button", "action": "export_csv"},
                    {"label": "Copy JSON", "type": "button", "action": "copy_json"},
                    {"label": "Send to Tutor", "type": "button", "action": "send_tutor"}
                ]
            }
        }

    # === Overall Scores ===
    total_words = len(all_results)
    correct_count = sum(1 for r in all_results if r["points"] == r["max_points"])
    overall_acc = (correct_count / total_words * 100) if total_words else 0

    phonics_pct = (sum(r["points"] for r in phonics) / sum(r["max_points"] for r in phonics) * 100)
    sight_pct   = (sum(r["points"] for r in sight) / sum(r["max_points"] for r in sight) * 100) if sight else 0

    variance = abs(phonics_pct - sight_pct) if sight else 0
    avg_score = (phonics_pct + sight_pct) / 2 if sight else phonics_pct
    confidence = ("High" if variance < 20 and avg_score > 70 else
                  "Medium" if variance < 20 and avg_score > 40 else "Low")

    # === NEW: 75% Mastery = Strength ===
    from collections import defaultdict

    skill_stats = defaultdict(lambda: {"tested": 0, "correct": 0})

    for r in phonics:
        word = r["word"]
        correct = r["points"] == r["max_points"]
        word_data = word_lists[result_grade]["regular_words"].get(word, {})
        for feature, value in word_data.items():
            if feature == "sentence" or not value or value in ["-", ""]:
                continue
            display_name = {
                "beginning": "Beginning consonant",
                "final": "Ending consonant",
                "short_vowels": "Short vowel",
                "consonant_digraphs": "Consonant digraph",
                "consonant_blends": "Consonant blend",
                "long_vowel_patterns": "Long vowel pattern",
                "other_vowel_patterns": "Other vowel pattern",
                "inflected_endings": "Inflected ending",
                "beginning_consonant": "Beginning consonant",
                "final_consonant": "Ending consonant",
                "short_vowel": "Short vowel",
                "digraph": "Consonant digraph",
                "blend": "Consonant blend",
                "long_vowel": "Long vowel pattern",
                "other_vowel": "Other vowel pattern",
                "inflected": "Inflected ending"
            }.get(feature, feature)
            skill_stats[display_name]["tested"] += 1
            if correct:
                skill_stats[display_name]["correct"] += 1

    # === Build strengths & focus_areas (75% rule) ===
    strengths = []
    focus_areas = []
    key_error_patterns = []

    for skill, stats in skill_stats.items():
        tested = stats["tested"]
        correct = stats["correct"]
        pct = (correct / tested) * 100
        errors = tested - correct

        if pct >= 75:
            strengths.append(skill)
        if errors >= 2:
            focus_areas.append(skill)
        if errors > 0:
            key_error_patterns.append({"pattern": skill, "count": errors})

    # === Evaluation & Recommendation ===
    evaluation = evaluate_test(all_results, result_grade)
    recommendation = get_recommendation(
        {f"{k} error": (stats["tested"] - stats["correct"]) for k, stats in skill_stats.items()},
        evaluation["status"], all_results, result_grade
    )

    # === Placement ===
    placement = {"Above": "Above Grade Level", "At": "At Grade Level", "Below": "Below Grade Level"}[evaluation["status"]]
    next_step = "Unlock Next Grade" if evaluation["status"] == "Above" and result_grade != "Third" else \
                "Unlock Next Test" if evaluation["status"] == "Above" else "Continue current grade"
    grade_band = "K-3rd" if result_grade in ["Kindergarten", "First", "Second", "Third"] else result_grade

    # === Table Data ===
    table_data = [
        {
            "word": r["word"],
            "attempt": r["user_input"],
            "correct": r["points"] == r["max_points"],
            "error_type": next((k for k, v in r.get("mistakes", {}).items() if k != "spelling"), None)
                          or ("Sight word" if r["type"] == "sight" and not r["points"] else None),
            "time": r.get("time", 0.0),
            "hints_used": r.get("hints_used", 0),
            "icon": "Correct" if r["points"] == r["max_points"] else "Incorrect"
        }
        for r in all_results
    ]

    # === Final Response – 100% SAME AS BEFORE ===
    return {
        "user_id": user_id,
        "child_id": request.child_id,
        "grade": result_grade,
        "parent_summary": {
            "overall_accuracy": round(overall_acc),
            "phonics_score": round(phonics_pct),
            "sight_word_score": round(sight_pct),
            "confidence": confidence,
            "key_error_patterns": key_error_patterns,
            "strengths": strengths,           # Now 75%+ correct
            "focus_areas": focus_areas,       # 2+ errors
            "recommendation": recommendation,
            "note": "Note: Placement is instructional and not a clinical diagnosis.",
            "grade_band": {"band": grade_band, "placement": placement, "next_step": next_step},
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

@app.post("/feedback/")
async def submit_feedback(feedback: FeedbackRequest):
    try:
        # Verify token and get user info
        decoded = auth.verify_id_token(feedback.idToken)
        user_id = decoded["uid"]
        user_email = decoded.get("email", "unknown@example.com")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    # Optional: Still verify child exists (for security)
    if not db_ref.child(f"users/{user_id}/children/{feedback.child_id}").get():
        raise HTTPException(status_code=404, detail="Child not found")

    feedback_id = str(uuid.uuid4())

    # Save under parent_feedback/
    payload = {
        "user_id": user_id,
        "email": user_email,
        "child_id": feedback.child_id,
        "answers": {
            "What grade is your child currently in?": feedback.q1_grade,
            "Has your child taken spelling assessments before?": feedback.q2_prior_assessments,
            "How confident is your child typically with spelling?": feedback.q3_spelling_confidence,
            "How did you find the length of this assessment?": feedback.q4_assessment_length,
            "How would you rate the difficulty level for your child?": feedback.q5_difficulty_level,
            "How engaged was your child during the assessment?": feedback.q6_engagement_level,
            "Did you experience any technical difficulties?": feedback.q7_technical_issues,
            "How clear and understandable are the results?": feedback.q8_results_clarity,
            "How helpful are the recommendations provided?": feedback.q9_recommendations_helpful,
            "Is the amount of information provided appropriate?": feedback.q10_information_amount,
            "Overall, how satisfied are you with this spelling assessment?": feedback.q11_overall_satisfaction,
            "Any additional comments or suggestions?": feedback.q12_comments.strip()
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    try:
        # Save under parent_feedback/
        db_ref.child("parent_feedback").child(feedback_id).set(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")

    return {
        "message": "Feedback saved successfully",
        "feedback_id": feedback_id,
        "saved_under": "parent_feedback",
        "email": user_email,
        "timestamp": payload["timestamp"]
    }
# === ADMIN: MAKE USER ADMIN ===
# === ADMIN: MAKE USER ADMIN BY EMAIL ===
@app.post("/admin/make-admin/")
async def make_admin(request: MakeAdminRequest):
    try:
        # === 1. Verify caller is admin ===
        decoded = auth.verify_id_token(request.idToken)
        caller_uid = decoded["uid"]

        caller_data = db_ref.child("users").child(caller_uid).get()
        if not caller_data or not caller_data.get("isAdmin", False):
            raise HTTPException(status_code=403, detail="Only admins can promote users")

        # === 2. Find target user by email ===
        target_email = request.targetEmail.strip().lower()
        all_users = db_ref.child("users").get() or {}

        target_uid = None
        for uid, data in all_users.items():
            if data.get("email", "").strip().lower() == target_email:
                target_uid = uid
                break

        if not target_uid:
            raise HTTPException(status_code=404, detail=f"User with email '{target_email}' not found")

        # === 3. Update isAdmin = true ===
        db_ref.child("users").child(target_uid).update({"isAdmin": True})

        return {
            "message": f"User {target_email} is now an admin",
            "updated": True,
            "targetUid": target_uid  # Optional: helpful for logs
        }

    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
@app.post("/admin/stats/")
async def get_admin_stats(request: GetDetailsRequest):
    try:
        # === 1. Verify token & get UID ===
        decoded = auth.verify_id_token(request.idToken)
        current_uid = decoded["uid"]
        current_user = db_ref.child("users").child(current_uid).get()
        if not current_user or not current_user.get("isAdmin", False):
            return {
                "isAdmin": False,
                "totalUsers": 0,
                "users": []
            }

        # === 2. Fetch ALL users from Realtime DB ===
        all_users_raw = db_ref.child("users").get() or {}
        user_list = []

        for uid, data in all_users_raw.items():
            email = data.get("email", "N/A")

            # === GET REAL CREATION TIME FROM FIREBASE AUTH ===
            try:
                auth_user = firebase_auth.get_user(uid)
                created_at = int(auth_user.user_metadata.creation_timestamp / 1000)  # ms → sec
            except:
                # Fallback: use DB createdAt or estimate
                created_at = data.get("createdAt")
                if not created_at or not isinstance(created_at, (int, float)):
                    created_at = int(time.time()) - (30 * 24 * 3600)  # 30 days ago as fallback

            # Format date
            joined_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(created_at))

            user_list.append({
                "email": email,
                "joinedDate": joined_date,
                "timestamp": created_at
            })

        # === 3. Sort: Newest first ===
        user_list.sort(key=lambda x: x["timestamp"], reverse=True)

        # === 4. Final output ===
        final_users = [
            {"email": u["email"], "joinedDate": u["joinedDate"]}
            for u in user_list
        ]

        return {
            "isAdmin": True,
            "totalUsers": len(final_users),
            "users": final_users
        }

    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/admin/feedback/")
async def get_all_feedback(request: GetDetailsRequest):
    try:
        # Verify Firebase ID token
        decoded_token = auth.verify_id_token(request.idToken)
        uid = decoded_token["uid"]

        # Fetch user data from Firebase Realtime DB
        user_data = db_ref.child("users").child(uid).get()
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        # Check isAdmin flag in DB
        if not user_data.get("isAdmin", False):
            raise HTTPException(status_code=403, detail="Admin access required")

    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid ID token")
    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")

    # Only admins reach here
    feedbacks = db_ref.child("parent_feedback").get() or {}
    feedback_list = list(feedbacks.values())

    return {
        "count": len(feedback_list),
        "feedbacks": feedback_list
    }

# ==================== SPEAKING TEST APIs ====================

# ==================== OPENAI SPEECH FUNCTIONS ====================

async def transcribe_audio_with_openai(audio_base64: str, audio_format: str = "mp3") -> Dict:
    """
    Use OpenAI Whisper to transcribe audio and get word-level timestamps.
    """
    if not openai_client:
        return {
            "success": False,
            "error": "OpenAI API key not configured",
            "transcribed_text": "",
            "word_timestamps": []
        }
    
    try:
        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_base64)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name
        
        # Transcribe with Whisper
        with open(temp_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
        
        # Clean up temp file
        os.unlink(temp_path)
        
        # Extract word timestamps if available
        word_timestamps = []
        if hasattr(transcript, 'words') and transcript.words:
            for word_info in transcript.words:
                word_timestamps.append({
                    "word": word_info.word,
                    "start": word_info.start,
                    "end": word_info.end
                })
        
        return {
            "success": True,
            "transcribed_text": transcript.text,
            "word_timestamps": word_timestamps,
            "duration": transcript.duration if hasattr(transcript, 'duration') else 0
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "transcribed_text": "",
            "word_timestamps": []
        }


async def analyze_speech_with_openai(original_sentence: str, transcribed_text: str, word_timestamps: List[Dict], duration_seconds: float, grade: str) -> Dict:
    """
    Use OpenAI GPT to perform comprehensive speech analysis.
    """
    if not openai_client:
        return {
            "success": False,
            "error": "OpenAI API key not configured",
            "analysis": None
        }
    
    try:
        # Build the analysis prompt
        prompt = f"""You are an expert speech therapist and language teacher for children. Analyze the following speech sample from a {grade} grade student.

ORIGINAL SENTENCE (what they should say):
"{original_sentence}"

WHAT THE CHILD ACTUALLY SAID (transcribed):
"{transcribed_text}"

WORD TIMING DATA:
{json.dumps(word_timestamps, indent=2) if word_timestamps else "No detailed timing available"}

TOTAL DURATION: {duration_seconds} seconds
EXPECTED WORD COUNT: {len(original_sentence.split())}
ACTUAL WORD COUNT: {len(transcribed_text.split())}

Please analyze and provide scores (0-100) and feedback for:

1. PRONUNCIATION ACCURACY: How accurately did the child pronounce each word?
2. SPEAKING RATE/PACE: Is their speaking speed appropriate? (normal for children: 100-150 WPM)
3. FLUENCY & GAPS: How smoothly did they speak? (pauses > 1 second are concerning)
4. GRAMMAR & WORD ORDER: Did they maintain correct grammar?

Respond in this exact JSON format:
{{
    "pronunciation": {{
        "score": <0-100>,
        "correct_words": <number>,
        "total_words": <number>,
        "mispronounced_words": [
            {{"expected": "word", "heard": "what_child_said", "feedback": "specific tip"}}
        ],
        "feedback": "child-friendly feedback"
    }},
    "speaking_rate": {{
        "score": <0-100>,
        "wpm": <calculated words per minute>,
        "status": "Too Slow/Slightly Slow/Perfect/Slightly Fast/Too Fast",
        "feedback": "child-friendly feedback"
    }},
    "fluency": {{
        "score": <0-100>,
        "long_pauses_count": <number>,
        "feedback": "child-friendly feedback"
    }},
    "grammar": {{
        "score": <0-100>,
        "issues": [
            {{"type": "missing_word/extra_word/wrong_order", "detail": "description"}}
        ],
        "feedback": "child-friendly feedback"
    }},
    "overall": {{
        "score": <weighted average>,
        "status": "Above/At/Below",
        "level": "Excellent Speaker/Good Speaker/Developing Speaker",
        "strengths": ["list of strengths"],
        "areas_to_improve": ["list of areas"],
        "recommendation": "personalized recommendation for the child",
        "parent_tip": "tip for parents to help"
    }}
}}"""

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a child speech analysis expert. Always respond with valid JSON only, no markdown formatting."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
        # Parse the response
        result_text = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = re.sub(r'^```json?\s*', '', result_text)
            result_text = re.sub(r'\s*```$', '', result_text)
        
        analysis = json.loads(result_text)
        
        return {
            "success": True,
            "analysis": analysis
        }
        
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse AI response: {str(e)}",
            "analysis": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "analysis": None
        }




# ==================== SPEAKING API ENDPOINTS ====================

@app.post("/speaking/get_sentence/")
async def get_speaking_sentence(request: SpeakingSentenceRequest):
    """Get a sentence for speaking test based on grade."""
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    # Verify child exists
    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")
    
    grade = request.grade
    if grade not in speaking_sentences:
        raise HTTPException(status_code=400, detail="Invalid grade. Must be: Kindergarten, First, Second, or Third")
    
    # Get sentences for the grade and shuffle
    sentences = speaking_sentences[grade].copy()
    random.shuffle(sentences)
    
    # Generate audio for the sentence using Polly
    selected = sentences[0]
    sentence_ssml = f'<speak><prosody rate="90%">{selected["sentence"]}</prosody></speak>'
    
    try:
        audio_response = polly_client.synthesize_speech(
            Text=sentence_ssml,
            TextType='ssml',
            OutputFormat='mp3',
            VoiceId='Joanna',
            Engine='neural',
            LanguageCode='en-US'
        )
        audio_base64 = base64.b64encode(audio_response['AudioStream'].read()).decode('utf-8')
    except Exception as e:
        audio_base64 = None
    
    return {
        "grade": grade,
        "sentence_id": selected["id"],
        "sentence": selected["sentence"],
        "word_count": selected["word_count"],
        "difficulty": selected["difficulty"],
        "audio_base64": audio_base64,
        "instructions": "Listen to the sentence, then record yourself saying it clearly."
    }


@app.post("/speaking/get_all_sentences/")
async def get_all_speaking_sentences(request: SpeakingSentenceRequest):
    """Get all sentences for a speaking test with audio."""
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")
    
    grade = request.grade
    if grade not in speaking_sentences:
        raise HTTPException(status_code=400, detail="Invalid grade")
    
    sentences = speaking_sentences[grade].copy()
    random.shuffle(sentences)
    
    result_sentences = []
    for sent in sentences:
        try:
            sentence_ssml = f'<speak><prosody rate="90%">{sent["sentence"]}</prosody></speak>'
            audio_response = polly_client.synthesize_speech(
                Text=sentence_ssml,
                TextType='ssml',
                OutputFormat='mp3',
                VoiceId='Joanna',
                Engine='neural',
                LanguageCode='en-US'
            )
            audio_base64 = base64.b64encode(audio_response['AudioStream'].read()).decode('utf-8')
        except:
            audio_base64 = None
        
        result_sentences.append({
            "sentence_id": sent["id"],
            "sentence": sent["sentence"],
            "word_count": sent["word_count"],
            "difficulty": sent["difficulty"],
            "audio_base64": audio_base64
        })
    
    return {
        "grade": grade,
        "total_sentences": len(result_sentences),
        "sentences": result_sentences
    }


@app.post("/speaking/analyze/")
async def analyze_speaking(request: SpeakingAnalyzeRequest):
    """
    Analyze child's speech from base64 audio.
    1. Transcribes audio using OpenAI Whisper
    2. Analyzes speech using GPT-4o
    3. Returns detailed scores and feedback
    """
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")
    
    grade = request.grade
    if grade not in speaking_sentences:
        raise HTTPException(status_code=400, detail="Invalid grade")
    
    original = request.original_sentence
    
    # Step 1: Transcribe audio with OpenAI Whisper
    transcription_result = await transcribe_audio_with_openai(request.audio_base64, request.audio_format)
    
    if not transcription_result["success"]:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {transcription_result.get('error', 'Unknown error')}")
    
    transcribed = transcription_result["transcribed_text"]
    word_timestamps = transcription_result["word_timestamps"]
    duration = transcription_result.get("duration", 0)
    
    # Step 2: Analyze with GPT-4o
    ai_result = await analyze_speech_with_openai(original, transcribed, word_timestamps, duration, grade)
    
    if ai_result["success"] and ai_result["analysis"]:
        analysis = ai_result["analysis"]
        return {
            "original_sentence": original,
            "transcribed_text": transcribed,
            "duration_seconds": duration,
            "word_timestamps": word_timestamps,
            "analysis_method": "openai_gpt4",
            "pronunciation": analysis.get("pronunciation", {}),
            "speaking_rate": analysis.get("speaking_rate", {}),
            "fluency": analysis.get("fluency", {}),
            "grammar": analysis.get("grammar", {}),
            "overall": analysis.get("overall", {}),
            "recommendation": analysis.get("overall", {}).get("recommendation", ""),
            "parent_tip": analysis.get("overall", {}).get("parent_tip", "")
        }
    
    raise HTTPException(status_code=500, detail="Speech analysis failed. Please try again later.")


@app.post("/speaking/submit/")
async def submit_speaking_test(request: SpeakingSubmitRequest):
    """
    Enhanced: Always submit all sentences for the grade. For unanswered sentences, mark as 'Not Attempted'. Only score answered ones.
    """
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")

    grade = request.grade
    if grade not in speaking_sentences:
        raise HTTPException(status_code=400, detail="Invalid grade")

    # Get all sentences for the grade
    all_sentences = speaking_sentences[grade]
    sentence_map = {s["id"]: s for s in all_sentences}

    # Build a map of submitted answers (if any)
    submitted = {}
    if hasattr(request, "submissions") and request.submissions:
        for item in request.submissions:
            sid = item.get("sentence_id") if isinstance(item, dict) else item.sentence_id
            submitted[sid] = item
    elif hasattr(request, "sentence_id") and request.sentence_id:
        # Single submission backward compatible
        submitted[request.sentence_id] = {
            "sentence_id": request.sentence_id,
            "original_sentence": getattr(request, "original_sentence", ""),
            "audio_base64": getattr(request, "audio_base64", ""),
            "audio_format": getattr(request, "audio_format", "mp3")
        }

    results = []
    total_score = 0
    answered_count = 0
    total_sentences = len(all_sentences)
    for sent in all_sentences:
        sid = sent["id"]
        original = sent["sentence"]
        item = submitted.get(sid)
        audio_base64 = None
        audio_format = "mp3"
        if item is not None:
            if isinstance(item, dict):
                audio_base64 = item.get("audio_base64", "")
                audio_format = item.get("audio_format", "mp3")
            else:
                audio_base64 = getattr(item, "audio_base64", "")
                audio_format = getattr(item, "audio_format", "mp3")
        if audio_base64:
            transcription_result = await transcribe_audio_with_openai(audio_base64, audio_format)
            if not transcription_result["success"]:
                results.append({
                    "sentence_id": sid,
                    "original_sentence": original,
                    "transcription_error": transcription_result.get('error', 'Unknown'),
                    "transcribed_text": "",
                    "analysis": None,
                    "status": "Error"
                })
                continue
            transcribed = transcription_result["transcribed_text"]
            word_timestamps = transcription_result["word_timestamps"]
            duration = transcription_result.get("duration", 0)
            ai_result = await analyze_speech_with_openai(original, transcribed, word_timestamps, duration, grade)
            if ai_result["success"] and ai_result["analysis"]:
                analysis = ai_result["analysis"]
                analysis_method = "openai_gpt4"
                pronunciation = analysis.get("pronunciation", {})
                rate = analysis.get("speaking_rate", {})
                fluency = analysis.get("fluency", {})
                grammar = analysis.get("grammar", {})
                overall = analysis.get("overall", {})
                recommendation = overall.get("recommendation", "Keep practicing!")
            else:
                results.append({
                    "sentence_id": sid,
                    "original_sentence": original,
                    "transcribed_text": transcribed,
                    "analysis": None,
                    "status": "Analysis Error"
                })
                continue
            overall_score = overall.get("score", 0)
            total_score += overall_score
            answered_count += 1
            results.append({
                "sentence_id": sid,
                "original_sentence": original,
                "transcribed_text": transcribed,
                "duration_seconds": duration,
                "pronunciation": pronunciation,
                "speaking_rate": rate,
                "fluency": fluency,
                "grammar": grammar,
                "overall": overall,
                "recommendation": recommendation,
                "analysis_method": analysis_method,
                "status": "Answered"
            })
        else:
            results.append({
                "sentence_id": sid,
                "original_sentence": original,
                "transcribed_text": "",
                "duration_seconds": 0,
                "pronunciation": {},
                "speaking_rate": {},
                "fluency": {},
                "grammar": {},
                "overall": {"score": 0, "status": "Not Attempted", "level": "Not Attempted"},
                "recommendation": "Not attempted.",
                "analysis_method": "",
                "status": "Not Attempted"
            })

    max_score = total_sentences * 100
    user_score = round(total_score, 1)
    percentage = round((user_score / max_score) * 100, 1) if max_score else 0
    # Level mapping based on percentage
    if percentage >= 90:
        level = "Excellent Speaker"
    elif percentage >= 75:
        level = "Good Speaker"
    elif percentage >= 50:
        level = "Developing Speaker"
    else:
        level = "Needs Improvement"
    avg_score = round(total_score / total_sentences, 1) if total_sentences else 0
    # Save the entire batch as a single test
    test_id = db_ref.child(f"users/{user_id}/children/{request.child_id}/speaking_tests").push().key
    test_data = {
        "grade": grade,
        "results": results,
        "total_marks": max_score,
        "user_score": user_score,
        "answered_count": answered_count,
        "average_score": avg_score,
        "percentage": percentage,
        "level": level,
        "timestamp": datetime.utcnow().isoformat()
    }
    db_ref.child(f"users/{user_id}/children/{request.child_id}/speaking_tests/{test_id}").set(test_data)

    return {
        "success": True,
        "user_id": user_id,
        "child_id": request.child_id,
        "grade": grade,
        "test_id": test_id,
        "total_marks": max_score,
        "user_score": user_score,
        "answered_count": answered_count,
        "average_score": avg_score,
        "percentage": percentage,
        "level": level,
        "results": results,
        "message": f"Submission completed: {answered_count} answered, {len(results) - answered_count} not attempted."
    }


@app.post("/speaking/complete_result/")
async def speaking_complete_result(request: SpeakingResultRequest):
    """Get complete speaking test results for a child."""
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Fetch all speaking test batches for the child and grade
    tests_data = db_ref.child(f"users/{user_id}/children/{request.child_id}/speaking_tests").get() or {}
    if not tests_data:
        raise HTTPException(status_code=404, detail="No speaking test results found")

    # Filter by grade if specified
    filtered = []
    for test_id, t in tests_data.items():
        g = t.get("grade")
        if request.grade and g != request.grade:
            continue
        filtered.append((t.get("timestamp", ""), t, test_id))
    if not filtered:
        raise HTTPException(status_code=404, detail=f"No speaking results for grade: {request.grade or 'any'}")

    # Sort by timestamp descending (latest first)
    filtered.sort(key=lambda x: x[0], reverse=True)
    latest_test = filtered[0][1]

    all_results = latest_test.get("results", [])
    user_score = latest_test.get("user_score", 0)
    answered_count = latest_test.get("answered_count", 0)
    avg_score = latest_test.get("average_score", 0)
    level = latest_test.get("level", "Developing Speaker")
    total_marks = latest_test.get("total_marks", 100)
    percentage = latest_test.get("percentage", 0)
    # Placement logic (optional, can be refined)
    if percentage >= 90:
        placement = "Above Grade Level"
    elif percentage >= 75:
        placement = "At Grade Level"
    else:
        placement = "Below Grade Level"

    return {
        "user_id": user_id,
        "child_id": request.child_id,
        "grade": latest_test.get("grade"),
        "total_marks": total_marks,
        "user_score": user_score,
        "answered_count": answered_count,
        "average_score": avg_score,
        "percentage": percentage,
        "level": level,
        "parent_summary": {
            "level": level,
            "recommendation": "See detailed feedback for each sentence.",
            "grade_placement": placement,
            "note": "Assessment is instructional and not a clinical diagnosis."
        },
        "all_results": all_results
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)