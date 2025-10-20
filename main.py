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

# Initialize FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
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
    time: float = 0.0  # Default to 0 if not provided
    hints_used: int = 0  # Default to 0 if not provided

class SubmitWordsRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str
    words: List[WordInput]

class UserCreate(BaseModel):
    idToken: str
    email: str
    name: str
    password: str  # Added for registration
    age: int

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

            # Short e
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
       
        "sight_words": {
            "to": {"sentence": "The dog is big."},
            "me": {"sentence": "I like cats and dogs."},
            "he": {"sentence": "It is sunny today."},
            "see": {"sentence": "Do you like to play?"},
            "go": {"sentence": "That is my toy."},
            "no": {"sentence": "He was at the park."},
            "a": {"sentence": "This is for you."},
            "it": {"sentence": "We are friends."},
            "in": {"sentence": "Play with me."},
            "on": {"sentence": "This is his ball."}
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
        "nonsense_words": {
            "som": {"sentence": "The wizard found a magical som in the forest."},
            "jat": {"sentence": "She wore a shiny jat on her head."},
            "ket": {"sentence": "The ket buzzed around the colorful flowers."},
            "zix": {"sentence": "He discovered a tiny zix in his pocket."},
            "vut": {"sentence": "The vut glowed brightly in the dark cave."}
        },
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
        "nonsense_words": {
            "sprill": {"sentence": "The sprill sparkled in the moonlight."},
            "slaff": {"sentence": "He tripped over the slaff on the floor."},
            "plont": {"sentence": "She planted a plont in the garden."},
            "gress": {"sentence": "The gress grew tall in the meadow."},
            "flunt": {"sentence": "The flunt floated high above the trees."}
        },
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
        "nonsense_words": {
            "plet": {"sentence": "The plet rolled down the hill."},
            "mast": {"sentence": "She found a shiny mast in the cave."},
            "flemp": {"sentence": "The flemp glowed in the dark."},
            "stum": {"sentence": "He tripped over a stum in the forest."},
            "spon": {"sentence": "The spon floated on the lake."}
        },
        "sight_words": {
            "there": {"sentence": "There is a bird in the tree."},
            "which": {"sentence": "Which book do you like best?"},
            "although": {"sentence": "Although it was raining, we went outside."},
            "people": {"sentence": "Many people came to the party."},
            "could": {"sentence": "I could hear the music from far away."}
        }
    }
}

# Scoring and evaluation functions
def score_response(word: str, user_input: str, grade: str, word_type: str) -> Dict:
    user_input = user_input.strip().encode('ascii', 'ignore').decode('ascii').lower()
    
    if word_type == "sight" or word_type == "nonsense":
        if word.lower() == user_input:
            return {"points": 1, "max_points": 1, "mistakes": {}}
        else:
            return {"points": 0, "max_points": 1, "mistakes": {"spelling": f"Expected '{word}', got '{user_input}'"}}
    
    word_data = word_lists.get(grade, {}).get("regular_words", {}).get(word, {})
    if not word_data:
        return {"points": 0, "max_points": 0, "mistakes": {"invalid": "Word not in list"}}

    points = 0
    skill_mistakes = {}
    
    feature_mapping = {
        "Kindergarten": [
            "beginning", "final", "short_vowels", "consonant_digraphs", 
            "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"
        ],
        "First": [
            "beginning", "final", "short_vowel", "digraph", 
            "blend", "long_vowel", "other_vowel", "inflected"
        ],
        "Second": [
            "beginning_consonant", "final_consonant", "short_vowels", "consonant_digraphs", 
            "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"
        ]
    }
    
    features = feature_mapping.get(grade, feature_mapping["Second"])
    for feature in features:
        expected_value = word_data.get(feature, "-")
        if expected_value == "-" or expected_value == "":
            continue
        expected_value = expected_value.strip().encode('ascii', 'ignore').decode('ascii')
        if feature in ["beginning", "beginning_consonant"]:
            actual_consonant = expected_value.split()[0] if " " in expected_value else expected_value
            if user_input.startswith(actual_consonant.lower()):
                points += 1
            else:
                skill_mistakes[feature] = expected_value
        elif feature in ["final", "final_consonant"]:
            final_parts = [c.strip() for c in expected_value.split(",") if c.strip()]
            expected_ending = "".join(final_parts)
            long_v = word_data.get("long_vowel" if grade == "First" else "long_vowel_patterns", "-")
            inflected = word_data.get("inflected" if grade == "First" else "inflected_endings", "-")
            if "-" in long_v:
                v, _, e = long_v.partition("-")
                if e == "e" and inflected in ["-", ""] and "e" not in expected_ending.lower():
                    expected_ending += "e"
            if user_input.endswith(expected_ending):
                points += 1
            else:
                skill_mistakes[feature] = expected_value
        elif feature in ["long_vowel", "long_vowel_patterns"] and expected_value:
            if "-" in expected_value:
                vowel, _, end = expected_value.partition("-")
                vowel_pos = user_input.find(vowel.lower())
                end_pos = user_input.find(end.lower())
                inflected = word_data.get("inflected" if grade == "First" else "inflected_endings", "-")
                if end == "e" and inflected not in ["-", ""]:
                    is_valid = vowel_pos != -1
                else:
                    is_valid = vowel_pos != -1 and end_pos != -1 and vowel_pos < end_pos
                if is_valid:
                    points += 1
                else:
                    skill_mistakes[feature] = expected_value
            else:
                if expected_value.lower() in user_input:
                    points += 1
                else:
                    skill_mistakes[feature] = expected_value
        elif feature in ["short_vowel", "short_vowels", "other_vowel", "other_vowel_patterns", 
                         "digraph", "consonant_digraphs", "blend", "consonant_blends", 
                         "inflected", "inflected_endings"]:
            expected_values = [v.strip() for v in expected_value.split(",") if v.strip()]
            if any(ev.lower() in user_input for ev in expected_values):
                points += 1
            else:
                skill_mistakes[feature] = expected_value
        else:
            skill_mistakes[feature] = expected_value
    max_points = len([f for f in features if word_data.get(f) not in ["-", ""]])
    return {"points": points, "max_points": max_points, "mistakes": skill_mistakes}

def evaluate_test(results: List[Dict], grade: str) -> Dict:
    total_points = sum(result["points"] for result in results)
    max_points = sum(result["max_points"] for result in results)
    mistakes = sum(1 for result in results if result["points"] == 0)
    if mistakes >= 7:
        return {"status": "stopped", "score": total_points, "max_score": max_points}
    word_count = len(results)
    correct_count = sum(1 for result in results if result["points"] == result["max_points"])
    if grade == "Kindergarten" and word_count == 25:
        status = "At" if 18 <= correct_count <= 25 else ("Below" if correct_count < 18 else "Above")
    elif grade == "First" and word_count == 30:
        status = "At" if 22 <= correct_count <= 30 else ("Below" if correct_count < 22 else "Above")
    elif grade == "Second" and word_count == 26:
        status = "At" if 20 <= correct_count <= 26 else ("Below" if correct_count < 20 else "Above")
    else:
        status = "Below"
    return {
        "status": status,
        "score": total_points,
        "max_score": max_points,
        "words_tested": word_count,
        "correct_count": correct_count
    }

def analyze_errors(results: List[Dict], grade: str) -> Dict:
    feature_mapping = {
        "Kindergarten": [
            "beginning", "final", "short_vowels", "consonant_digraphs", 
            "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"
        ],
        "First": [
            "beginning", "final", "short_vowel", "digraph", 
            "blend", "long_vowel", "other_vowel", "inflected"
        ],
        "Second": [
            "beginning_consonant", "final_consonant", "short_vowels", "consonant_digraphs", 
            "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"
        ]
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
        # Dynamically determine a starting letter based on beginning consonant errors
        beginning_errors = [r for r in results if r.get("type") == "regular" and "beginning" in r.get("mistakes", {}) or "beginning_consonant" in r.get("mistakes", {})]
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
    if grade not in ["Kindergarten", "First", "Second"]:
        raise HTTPException(status_code=400, detail="Invalid grade")
    
    words_to_test = []
    regular = [
        {"word": word, "sentence": data["sentence"], "type": "regular"}
        for word, data in word_lists[grade]["regular_words"].items()
    ]
    nonsense = [
        {"word": word, "sentence": data["sentence"], "type": "nonsense"}
        for word, data in word_lists[grade]["nonsense_words"].items()
    ]
    sight = [
        {"word": word, "sentence": data["sentence"], "type": "sight"}
        for word, data in word_lists[grade]["sight_words"].items()
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
            "age": user.age
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
            "age": user_data.age,
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
        if not child.name or child.age < 0 or child.grade not in ["Kindergarten", "First", "Second"]:
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found or does not belong to user")
    grade = request.grade
    if grade not in ["Kindergarten", "First", "Second"]:
        raise HTTPException(status_code=400, detail="Invalid grade provided")
    results = []
    analysis = []
    for word_data in request.words:
        word = word_data.word
        user_input = word_data.user_input
        word_type = word_data.type
        time = word_data.time  # Capture time from client request
        hints_used = word_data.hints_used  # Capture hints used from client request
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
    assessment_summary = {
        "Phonics": {
            "score": sum(r["points"] for r in results if r["type"] == "regular"),
            "max_score": sum(r["max_points"] for r in results if r["type"] == "regular"),
            "percentage": (sum(r["points"] for r in results if r["type"] == "regular") / sum(r["max_points"] for r in results if r["type"] == "regular") * 100) if sum(r["max_points"] for r in results if r["type"] == "regular") > 0 else 0
        },
        "Sight Words": {
            "score": sum(r["points"] for r in results if r["type"] == "sight"),
            "max_score": sum(r["max_points"] for r in results if r["type"] == "sight"),
            "percentage": (sum(r["points"] for r in results if r["type"] == "sight") / sum(r["max_points"] for r in results if r["type"] == "sight") * 100) if sum(r["max_points"] for r in results if r["type"] == "sight") > 0 else 0
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
    # Validate Firebase token_id (ID token from Firebase Auth)
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token['uid']  # Extract user ID for tracking
        print(f"Authenticated user: {user_id}")  # Log for debugging (remove in production)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    word = request.text
    word_text = word
    try:
        # Generate audio for the word
        word_response = polly_client.synthesize_speech(
            Text=word_text,
            OutputFormat='mp3',
            VoiceId='Joanna'
        )
        word_audio = word_response['AudioStream'].read()
        
        
        
        # Encode audio as base64
        word_base64 = base64.b64encode(word_audio).decode('utf-8')
        
        return {
            
            "base64_audio": word_base64,
          
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate audio: {str(e)}")

@app.post("/generate_all_grade_audio/")
async def generate_all_kindergarten_audio(request: GradeInput):
    grade = request.grade
    
    try:
        audio_files = []
        # Iterate through all word types: regular, nonsense, sight
        for word_type in ["regular_words", "nonsense_words", "sight_words"]:
            words_dict = word_lists[grade][word_type]
            for word, data in words_dict.items():
                # Generate audio for the word
                word_ssml = f'<speak><prosody rate="95%">{word}</prosody></speak>'
                word_response = polly_client.synthesize_speech(
                    Text=word_ssml,
                    TextType='ssml',
                    OutputFormat='mp3',
                    VoiceId='Joanna'
                )
                word_audio = word_response['AudioStream'].read()
                
                # Generate audio for the sentence
                sentence = data["sentence"]
                sentence_ssml = f'<speak><prosody rate="95%">{sentence}</prosody></speak>'
                sentence_response = polly_client.synthesize_speech(
                    Text=sentence_ssml,
                    TextType='ssml',
                    OutputFormat='mp3',
                    VoiceId='Joanna'
                )
                sentence_audio = sentence_response['AudioStream'].read()
                
                # Encode audio as base64
                word_base64 = base64.b64encode(word_audio).decode('utf-8')
                sentence_base64 = base64.b64encode(sentence_audio).decode('utf-8')
                
                # Add to response
                audio_files.append({
                    "word": word,
                    "word_type": word_type.replace("_words", ""),
                    "word_audio": word_base64,
                    "sentence_audio": sentence_base64,
                    "word_filename": f"{word_type}/{word}_word.mp3",
                    "sentence_filename": f"{word_type}/{word}_sentence.mp3"
                })
        
        return {"grade": grade, "audio_files": audio_files}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate audio: {str(e)}")

@app.post("/complete_result/")
async def complete_result(request: CompleteResultRequest):
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found or does not belong to user")
    
    grade = child_data.get("grade", "Second") if not request.grade else request.grade
    if grade not in ["Kindergarten", "First", "Second"]:
        raise HTTPException(status_code=400, detail="Invalid grade")

    # Fetch all scores for the child
    scores_data = db_ref.child(f"users/{user_id}/children/{request.child_id}/scores").get() or {}
    # Sort scores by timestamp descending to get the latest
    sorted_scores = sorted(scores_data.items(), key=lambda x: x[1].get("timestamp", ""), reverse=True)
    if not sorted_scores:
        raise HTTPException(status_code=404, detail="No test results found for this child")
    
    # Get the latest score
    latest_score_id, latest_score_data = sorted_scores[0]
    if request.grade and latest_score_data.get("grade") != request.grade:
        raise HTTPException(status_code=404, detail="No results found for the specified grade in the latest test")

    # Use only the latest results
    all_results = latest_score_data.get("results", [])

    # Calculate overall metrics
    total_words = len(all_results)
    correct_count = sum(1 for r in all_results if r["points"] == r["max_points"])
    overall_accuracy = (correct_count / total_words * 100) if total_words > 0 else 0

    # Aggregate phonics and sight word scores
    phonics_results = [r for r in all_results if r["type"] == "regular"]
    sight_results = [r for r in all_results if r["type"] == "sight"]
    phonics_score = (sum(r["points"] for r in phonics_results) / sum(r["max_points"] for r in phonics_results) * 100) if phonics_results and sum(r["max_points"] for r in phonics_results) > 0 else 0
    sight_word_score = (sum(r["points"] for r in sight_results) / sum(r["max_points"] for r in sight_results) * 100) if sight_results and sum(r["max_points"] for r in sight_results) > 0 else 0

    # Improved confidence calculation
    score_variance = abs(phonics_score - sight_word_score) if phonics_results and sight_results else 0
    average_score = (phonics_score + sight_word_score) / 2 if phonics_results and sight_results else overall_accuracy
    if score_variance < 20:
        if average_score > 70:
            confidence = "High"
        elif average_score > 40:
            confidence = "Medium"
        else:
            confidence = "Low"
    else:
        confidence = "Low"

    # Analyze errors
    error_counts = analyze_errors(phonics_results, grade)
    key_error_patterns = [
        {"pattern": k.replace(" error", ""), "count": v}
        for k, v in error_counts.items() if v > 0
    ]

    # Determine strengths and focus areas
    strengths = [k.replace(" error", "") for k, v in error_counts.items() if v == 0 or v < 2]
    focus_areas = [k.replace(" error", "") for k, v in error_counts.items() if v >= 2]

    # Get evaluation and recommendation
    evaluation = evaluate_test(all_results, grade)
    recommendation = get_recommendation(error_counts, evaluation["status"], all_results, grade)

    # Determine grade band, placement, and next step dynamically
    grade_band = "K-2nd" if grade in ["Kindergarten", "First", "Second"] else f"{grade}"
    placement = {
        "Above": "At/Above Grade Level",
        "At": "At Grade Level",
        "Below": "Below Grade Level"
    }.get(evaluation["status"], "At Grade Level")
    next_step = "Unlock Grade 3 assessment" if evaluation["status"] == "Above" and grade == "Second" else "Continue current grade"

    # Prepare table data dynamically from all_results
    table_data = [
        {
            "word": r["word"],
            "attempt": r["user_input"],
            "correct": r["points"] == r["max_points"],
            "error_type": next((k for k, v in r.get("mistakes", {}).items() if k != "spelling"), None) or ("Sight word" if r["type"] == "sight" and not r["points"] else None),
            "time": r.get("time", 0.0),  # Use time from results, default to 0.0
            "hints_used": r.get("hints_used", 0),  # Use hints_used from results, default to 0
            "icon": "✓" if r["points"] == r["max_points"] else "✗"
        }
        for r in all_results
    ]

    # Construct response
    response = {
        "user_id": user_id,
        "child_id": request.child_id,
        "grade": grade,
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
            "test_level": grade,
            "words": total_words,
            "correct": correct_count,
            "instructional_level": grade,
            "table_data": table_data,
            "actions": [
                {"label": "Export CSV", "type": "button", "action": "export_csv"},
                {"label": "Copy JSON", "type": "button", "action": "copy_json"},
                {"label": "Send to Tutor", "type": "button", "action": "send_tutor"}
            ]
        }
    }
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)