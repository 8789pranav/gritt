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
import asyncio
from typing import Optional
from datetime import datetime
import boto3
from fastapi.responses import Response, FileResponse
import random
from logic_routes import (
    GetLogicTestRequest,
    SubmitLogicResponseRequest,
    SubmitLogicTestRequest,
    CompleteLogicResultRequest,
)
from logic_service import (
    get_logic_test_payload,
    score_logic_item_response,
    aggregate_logic_test_results,
    build_complete_logic_result,
)
from tagging_engine import (
    tag_logic_test,
    tag_spelling_test,
    tag_speaking_test,
    tag_comprehension_test,
    tag_logic_per_item,
    tag_spelling_per_word,
    tag_speaking_per_sentence,
    tag_comprehension_per_question,
)
from logic_assessment import ALL_LOGIC_ITEMS, get_items_by_grade, GradeLevel

# Initialize FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/logic/ui")
async def logic_ui():
    """Serve the logic assessment web UI."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "logic_test_web.html"))

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

# ==================== READING COMPREHENSION MODELS ====================
class ComprehensionQuestionAnswer(BaseModel):
    question_id: str
    selected_index: int  # 0-3 for options A-D

class ComprehensionStoryAnswer(BaseModel):
    story_id: str
    answers: List[ComprehensionQuestionAnswer]

class ComprehensionGetRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str

class ComprehensionSubmitRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str
    story_answers: List[ComprehensionStoryAnswer]

class ComprehensionResultRequest(BaseModel):
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

# ==================== READING COMPREHENSION STORIES ====================
# Stories written with emotional cues for expressive TTS narration
comprehension_stories = {
    "Kindergarten": [
        {
            "id": "k_story1",
            "title": "The Friendly Dog",
            "story": """Once upon a time, there was a small brown dog named Max. 
He lived in a cozy red house with a little boy named Tom.
Every morning, Max would wake up early and stretch his legs. Yaaawn!
He loved to run around in the yard. Zoom, zoom, zoom!
Tom would throw a bright yellow ball, and Max would catch it. Good boy, Max!
Max had a soft, fluffy bed near the window. It was his favorite spot.
He loved to sleep there after playing. Zzzzz...
One sunny day, Max found a new friend! Oh, how exciting!
It was a fluffy white cat named Fluffy. Meow!
They played together all day long. Chase, chase, chase!
Max was SO happy! He wagged his tail super fast and barked with joy. Woof woof!
Tom smiled and gave them both yummy treats. Munch, munch!
And from that day on, Max and Fluffy became the very best of friends. Forever and ever!
The End.""",
            "duration_estimate": "60 seconds",
            "questions": [
                {
                    "id": "k1_q1",
                    "question": "What color was Max the dog?",
                    "options": ["White", "Brown", "Black", "Yellow"],
                    "correct_index": 1
                },
                {
                    "id": "k1_q2",
                    "question": "What did Tom throw for Max?",
                    "options": ["A stick", "A bone", "A yellow ball", "A toy"],
                    "correct_index": 2
                },
                {
                    "id": "k1_q3",
                    "question": "What was the cat's name?",
                    "options": ["Fluffy", "Snowball", "Kitty", "Max"],
                    "correct_index": 0
                },
                {
                    "id": "k1_q4",
                    "question": "Where did Max like to sleep?",
                    "options": ["On the floor", "In Tom's bed", "Near the window", "Outside"],
                    "correct_index": 2
                }
            ]
        },
        {
            "id": "k_story2",
            "title": "The Magic Garden",
            "story": """Once upon a time, a little girl named Lily had a tiny garden behind her house.
She planted teeny-tiny seeds in the soft brown dirt. Pat, pat, pat!
Every single day, she gave them water from her special blue watering can. Splish, splash!
She talked sweetly to her plants and sang them little songs. La la la!
Then one sunny morning... Lily saw something AMAZING!
A tiny green leaf popped right up from the ground! Pop!
Lily was SO excited! She jumped up and down!
"Mommy, Mommy! Come see!" she called.
More and more leaves grew each day. Growing, growing, growing!
Then... WOW! Beautiful flowers bloomed everywhere!
There were red ones, pretty pink ones, and lovely purple ones too!
One day, a beautiful butterfly came to visit. Flutter, flutter!
It landed gently on the biggest red flower.
Lily smiled the biggest smile and clapped her happy hands. Clap, clap, clap!
Her garden was the most magical place in the whole wide world!
The End.""",
            "duration_estimate": "65 seconds",
            "questions": [
                {
                    "id": "k2_q1",
                    "question": "What color was Lily's watering can?",
                    "options": ["Red", "Green", "Blue", "Yellow"],
                    "correct_index": 2
                },
                {
                    "id": "k2_q2",
                    "question": "What came to visit Lily's garden?",
                    "options": ["A bird", "A butterfly", "A bee", "A ladybug"],
                    "correct_index": 1
                },
                {
                    "id": "k2_q3",
                    "question": "What did Lily do to help her plants grow?",
                    "options": ["She read to them", "She gave them water", "She painted them", "She played music"],
                    "correct_index": 1
                },
                {
                    "id": "k2_q4",
                    "question": "What color was NOT mentioned for the flowers?",
                    "options": ["Red", "Pink", "Orange", "Purple"],
                    "correct_index": 2
                }
            ]
        }
    ],
    "First": [
        {
            "id": "f_story1",
            "title": "The Lost Kitten",
            "story": """One rainy afternoon, drip drop drip drop, little Emma heard a tiny sound outside her window.
"Meow... meow..." What was that?
She looked outside and saw... oh no! A small gray kitten, all alone under a bush!
The poor little thing was wet and shivering. Brrr!
Emma's heart went out to the kitty. "I have to help!" she said.
She quickly grabbed an umbrella and ran outside. Splash, splash through the puddles!
Very gently, she picked up the scared little kitten. "It's okay, little one. I've got you."
She brought the kitten inside where it was warm and dry.
Her mother helped her wrap the kitten in a soft, fluffy towel. So cozy!
They gave the kitten some warm milk in a tiny bowl. Lap, lap, lap!
The kitten started to purr. Purrrr, purrrr! That meant it was happy!
Emma made a cozy little bed from her old blanket.
The next day, they put up signs everywhere. "Found: One adorable gray kitten!"
They waited... and waited... a whole week went by!
But nobody came to claim the sweet little kitten.
Emma's parents looked at each other and smiled. "Emma, would you like to keep her?"
"Really?! Oh, thank you, thank you, THANK YOU!" Emma was SO happy!
She named the kitten Misty, because she found her on that misty, rainy day.
And Emma and Misty became the very best of friends!
The End.""",
            "duration_estimate": "75 seconds",
            "questions": [
                {
                    "id": "f1_q1",
                    "question": "What was the weather like when Emma found the kitten?",
                    "options": ["Sunny", "Snowy", "Rainy", "Windy"],
                    "correct_index": 2
                },
                {
                    "id": "f1_q2",
                    "question": "What color was the kitten?",
                    "options": ["White", "Gray", "Orange", "Black"],
                    "correct_index": 1
                },
                {
                    "id": "f1_q3",
                    "question": "What did they give the kitten to drink?",
                    "options": ["Water", "Juice", "Warm milk", "Tea"],
                    "correct_index": 2
                },
                {
                    "id": "f1_q4",
                    "question": "Why did Emma name the kitten Misty?",
                    "options": ["Because it was gray", "Because of the rainy, misty day", "Because it had misty eyes", "Because her mom chose the name"],
                    "correct_index": 1
                }
            ]
        },
        {
            "id": "f_story2",
            "title": "The Birthday Surprise",
            "story": """Jake was SO excited! He was turning seven years old!
And he wanted something more than anything else in the whole wide world... a BICYCLE!
His old tricycle was way too small for him now. He was a big kid!
On his birthday morning, Jake woke up super early. His eyes popped open!
He jumped out of bed and ran downstairs as fast as he could. Thump, thump, thump!
The living room was AMAZING! Balloons everywhere! Red ones, blue ones, green ones floating in the air!
His mom and dad were smiling big smiles. "Happy Birthday, Jake!"
But wait... Jake looked around. Where was the bicycle? 
He didn't see one anywhere. Oh no...
He tried SO hard not to look sad. He put on a brave smile.
Then his dad said with a twinkle in his eye, "Jake... look in the garage!"
Jake's heart started beating fast. He ran to the garage and threw open the door!
And THERE IT WAS! 
A shiny, sparkly BLUE bicycle with silver handlebars! It was BEAUTIFUL!
"WOOOHOOO!" Jake jumped up and down like a bouncy ball!
He hugged his mom and dad super tight. "Thank you, thank you, THANK YOU!"
That afternoon, Dad taught Jake how to ride.
Wobble, wobble... CRASH! Jake fell down. Ouch!
But did he give up? NO WAY!
He got back up and tried again. Fall number two. Then fall number three!
But Jake never, ever gave up.
And by sunset, guess what? Jake could ride his bicycle ALL BY HIMSELF!
What a perfect birthday!
The End.""",
            "duration_estimate": "80 seconds",
            "questions": [
                {
                    "id": "f2_q1",
                    "question": "How old was Jake turning?",
                    "options": ["Five", "Six", "Seven", "Eight"],
                    "correct_index": 2
                },
                {
                    "id": "f2_q2",
                    "question": "What color was Jake's new bicycle?",
                    "options": ["Red", "Green", "Blue", "Yellow"],
                    "correct_index": 2
                },
                {
                    "id": "f2_q3",
                    "question": "Where was the bicycle hidden?",
                    "options": ["In his bedroom", "In the backyard", "In the garage", "In the basement"],
                    "correct_index": 2
                },
                {
                    "id": "f2_q4",
                    "question": "How many times did Jake fall while learning to ride?",
                    "options": ["One time", "Two times", "Three times", "Four times"],
                    "correct_index": 2
                }
            ]
        }
    ],
    "Second": [
        {
            "id": "s_story1",
            "title": "The Treasure Map",
            "story": "Sophie found an old piece of paper in her grandmother's attic. It looked like a treasure map with an X marked in red. The map showed her grandmother's backyard with trees and a small pond. Sophie decided to follow the map carefully. She walked past the old oak tree and turned left at the rose bushes. Then she counted ten steps toward the vegetable garden. The X was right next to the tomato plants. Sophie started digging with her small shovel. After a few minutes, she hit something hard. It was a metal box covered in rust. Her heart was beating fast with excitement. Inside the box, she found her grandmother's childhood treasures. There were old coins, pretty marbles, a silver locket with a photograph, and a letter. Her grandmother smiled when Sophie showed her. She told Sophie stories about each treasure. Sophie learned that the real treasure was the memories and stories from long ago.",
            "duration_estimate": "65 seconds",
            "questions": [
                {
                    "id": "s1_q1",
                    "question": "Where did Sophie find the treasure map?",
                    "options": ["In the basement", "In the attic", "In the kitchen", "In the garden"],
                    "correct_index": 1
                },
                {
                    "id": "s1_q2",
                    "question": "What was the X marked next to?",
                    "options": ["The oak tree", "The rose bushes", "The tomato plants", "The pond"],
                    "correct_index": 2
                },
                {
                    "id": "s1_q3",
                    "question": "What was inside the metal box?",
                    "options": ["Gold and diamonds", "Old coins, marbles, a locket, and a letter", "Toys and games", "Money and jewelry"],
                    "correct_index": 1
                },
                {
                    "id": "s1_q4",
                    "question": "According to the story, what was the real treasure?",
                    "options": ["The old coins", "The silver locket", "The memories and stories", "The metal box"],
                    "correct_index": 2
                }
            ]
        },
        {
            "id": "s_story2",
            "title": "The Science Fair Project",
            "story": "Marcus had two weeks to prepare for the school science fair. He decided to create a volcano that would actually erupt. His father helped him build a mountain shape using cardboard and paper. They painted it brown and gray to look like real rocks. Marcus researched how volcanoes work. He learned about magma deep inside the Earth. For the eruption, he would use baking soda and vinegar. On the day of the science fair, Marcus was nervous. Many students had impressive projects. Some made robots, others had plant experiments. When it was his turn, Marcus explained how volcanoes form. Then he poured the vinegar into the volcano. Red foam bubbled up and flowed down the sides like real lava. Everyone clapped and cheered. The judges were very impressed. Marcus won second place and received a blue ribbon. He felt proud of all his hard work and learning.",
            "duration_estimate": "62 seconds",
            "questions": [
                {
                    "id": "s2_q1",
                    "question": "How much time did Marcus have to prepare?",
                    "options": ["One week", "Two weeks", "Three weeks", "One month"],
                    "correct_index": 1
                },
                {
                    "id": "s2_q2",
                    "question": "What materials did Marcus use to make the volcano erupt?",
                    "options": ["Water and soap", "Baking soda and vinegar", "Oil and food coloring", "Salt and lemon juice"],
                    "correct_index": 1
                },
                {
                    "id": "s2_q3",
                    "question": "What place did Marcus win at the science fair?",
                    "options": ["First place", "Second place", "Third place", "He did not win"],
                    "correct_index": 1
                },
                {
                    "id": "s2_q4",
                    "question": "What color ribbon did Marcus receive?",
                    "options": ["Red", "Blue", "Yellow", "Green"],
                    "correct_index": 1
                }
            ]
        }
    ],
    "Third": [
        {
            "id": "t_story1",
            "title": "The Mysterious Letter",
            "story": "On a chilly October morning, twelve-year-old Aria discovered an unusual letter in her mailbox. It had no return address, just her name written in elegant cursive. Inside, she found a riddle that read: Where books sleep and knowledge grows, find the clue where the wise owl shows. Aria thought carefully about the riddle. The school library had an owl statue near the entrance! After school, she rushed to the library and searched around the owl. Behind a loose brick, she found another envelope. This riddle mentioned the place where stories come alive on stage. That meant the auditorium! She found the third clue taped under seat number forty-two. The final riddle led her to the old oak tree in the schoolyard. There, she discovered a small wooden box containing a beautiful journal and a note from her grandmother. The note explained that her grandmother had created this treasure hunt when she attended the same school fifty years ago. She wanted Aria to have her special journal filled with stories and poems. Aria realized her grandmother was sharing a piece of her childhood through this magical adventure.",
            "duration_estimate": "70 seconds",
            "questions": [
                {
                    "id": "t1_q1",
                    "question": "What time of year did Aria find the mysterious letter?",
                    "options": ["Spring", "Summer", "Fall/October", "Winter"],
                    "correct_index": 2
                },
                {
                    "id": "t1_q2",
                    "question": "Where did Aria find the first clue?",
                    "options": ["In the auditorium", "Behind the owl statue at the library", "Under a tree", "In her classroom"],
                    "correct_index": 1
                },
                {
                    "id": "t1_q3",
                    "question": "What seat number had the third clue?",
                    "options": ["Seat twenty-four", "Seat thirty-two", "Seat forty-two", "Seat fifty-two"],
                    "correct_index": 2
                },
                {
                    "id": "t1_q4",
                    "question": "Who created the treasure hunt and when?",
                    "options": ["Her mother, ten years ago", "Her grandmother, fifty years ago", "Her teacher, last year", "Her father, twenty years ago"],
                    "correct_index": 1
                }
            ]
        },
        {
            "id": "t_story2",
            "title": "The Courage to Try",
            "story": "Daniel had always been terrified of water. While his friends enjoyed swimming at the community pool, he sat on the sidelines watching. His fear began when he fell into a pond as a young child. His parents encouraged him to take swimming lessons, but he always refused. One summer, his family planned a trip to the beach. Daniel felt anxious for weeks. His older sister, Maya, noticed his worry and offered to help him. They started slowly at the shallow end of their neighbor's pool. Maya taught him to put his face in the water and blow bubbles. Each day, Daniel became a little braver. He learned to float on his back, then to kick his feet. By the end of three weeks, Daniel could swim across the pool. When the beach trip finally arrived, something amazing happened. Daniel walked into the ocean waves without fear. He splashed and played with his family for the first time. That evening, as the sun set over the water, Daniel realized that facing his fear had given him something wonderful, the confidence to try new things.",
            "duration_estimate": "68 seconds",
            "questions": [
                {
                    "id": "t2_q1",
                    "question": "Why was Daniel afraid of water?",
                    "options": ["He saw a scary movie", "He fell into a pond as a child", "His friend got hurt swimming", "He never learned to swim"],
                    "correct_index": 1
                },
                {
                    "id": "t2_q2",
                    "question": "Who helped Daniel overcome his fear?",
                    "options": ["His parents", "A swimming coach", "His older sister Maya", "His best friend"],
                    "correct_index": 2
                },
                {
                    "id": "t2_q3",
                    "question": "How long did it take Daniel to learn to swim across the pool?",
                    "options": ["One week", "Two weeks", "Three weeks", "One month"],
                    "correct_index": 2
                },
                {
                    "id": "t2_q4",
                    "question": "What important lesson did Daniel learn?",
                    "options": ["Swimming is easy", "The ocean is safe", "Facing fears gives confidence", "Sisters are helpful"],
                    "correct_index": 2
                }
            ]
        }
    ]
}

# ==================== COMPREHENSION QUESTION TYPE MAPPING ====================
# Each question classified as literal (explicit details), inferential (reasoning), or vocabulary
COMPREHENSION_QUESTION_TYPES = {
    # Kindergarten - Story 1: The Friendly Dog
    "k1_q1": "literal",       # What color was Max? (explicit detail)
    "k1_q2": "literal",       # What did Tom throw? (explicit detail)
    "k1_q3": "literal",       # What was the cat's name? (explicit detail)
    "k1_q4": "literal",       # Where did Max sleep? (explicit detail)
    # Kindergarten - Story 2: The Magic Garden
    "k2_q1": "literal",       # What color was watering can? (explicit detail)
    "k2_q2": "literal",       # What came to visit? (explicit detail)
    "k2_q3": "literal",       # What did Lily do to help plants? (explicit detail)
    "k2_q4": "inferential",   # What color NOT mentioned? (requires reasoning about negation)
    # First Grade - Story 1: The Lost Kitten
    "f1_q1": "literal",       # What was the weather? (explicit detail)
    "f1_q2": "literal",       # What color was kitten? (explicit detail)
    "f1_q3": "literal",       # What did they give kitten? (explicit detail)
    "f1_q4": "inferential",   # Why name Misty? (requires inference about naming reason)
    # First Grade - Story 2: The Birthday Surprise
    "f2_q1": "literal",       # How old was Jake? (explicit detail)
    "f2_q2": "literal",       # What color bicycle? (explicit detail)
    "f2_q3": "literal",       # Where was bicycle hidden? (explicit detail)
    "f2_q4": "literal",       # How many times fell? (explicit detail)
    # Second Grade - Story 1: The Treasure Map
    "s1_q1": "literal",       # Where found map? (explicit detail)
    "s1_q2": "literal",       # What was X next to? (explicit detail)
    "s1_q3": "literal",       # What was inside box? (explicit detail)
    "s1_q4": "inferential",   # What was the real treasure? (requires theme inference)
    # Second Grade - Story 2: The Science Fair
    "s2_q1": "literal",       # How much time? (explicit detail)
    "s2_q2": "literal",       # What materials? (explicit detail)
    "s2_q3": "literal",       # What place won? (explicit detail)
    "s2_q4": "vocabulary",    # What color ribbon? (contextual detail/vocabulary)
    # Third Grade - Story 1: The Mysterious Letter
    "t1_q1": "literal",       # What time of year? (explicit detail)
    "t1_q2": "literal",       # Where first clue? (explicit detail)
    "t1_q3": "literal",       # What seat number? (explicit detail)
    "t1_q4": "inferential",   # Who created hunt and when? (requires connecting details)
    # Third Grade - Story 2: The Courage to Try
    "t2_q1": "inferential",   # Why afraid of water? (cause-effect inference)
    "t2_q2": "literal",       # Who helped Daniel? (explicit detail)
    "t2_q3": "literal",       # How long to learn? (explicit detail)
    "t2_q4": "inferential",   # What lesson learned? (theme inference)
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
        "First": ["beginning", "final", "short_vowels", "consonant_digraphs", "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"],
        "Second": ["beginning", "final", "short_vowel", "digraph", "blend", "long_vowel", "other_vowel", "inflected"],
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
        "First": ["beginning", "final", "short_vowels", "consonant_digraphs", "consonant_blends", "long_vowel_patterns", "other_vowel_patterns", "inflected_endings"],
        "Second": ["beginning", "final", "short_vowel", "digraph", "blend", "long_vowel", "other_vowel", "inflected"],
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


def verify_child_and_token(id_token: str, child_id: str):
    try:
        decoded_token = auth.verify_id_token(id_token)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    child_data = db_ref.child(f"users/{user_id}/children/{child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")

    return user_id, child_data


@app.post("/logic/get_test/")
async def logic_get_test(request: GetLogicTestRequest):
    verify_child_and_token(request.idToken, request.child_id)
    response_payload = get_logic_test_payload(request.grade)
    return {"success": True, **response_payload}


async def generate_tts_audio(text: str, voice: str = "nova", speed: float = 0.85) -> str:
    """
    Shared TTS function for ALL tests (comprehension, speaking, spelling, logic).
    Uses OpenAI TTS nova voice (same as comprehension) for consistency.
    Falls back to AWS Polly Joanna neural if OpenAI is unavailable.

    Args:
        text: Text to synthesize
        voice: OpenAI voice name (default 'nova' - warm, child-friendly)
        speed: Playback speed (0.85 = slightly slower for children)
    Returns:
        Base64-encoded MP3 audio string, or None on failure
    """
    if not text or not text.strip():
        return None

    # Try OpenAI TTS first (nova - same voice as comprehension)
    if openai_client:
        try:
            response = openai_client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input=text.strip(),
                speed=speed,
            )
            return base64.b64encode(response.content).decode('utf-8')
        except Exception as e:
            print(f"OpenAI TTS error: {str(e)}")

    # Fallback to AWS Polly (Joanna neural)
    try:
        ssml = f'<speak><prosody rate="{int(speed * 100)}%">{text.strip()[:2900]}</prosody></speak>'
        audio_response = polly_client.synthesize_speech(
            Text=ssml,
            TextType='ssml',
            OutputFormat='mp3',
            VoiceId='Joanna',
            Engine='neural',
            LanguageCode='en-US',
        )
        return base64.b64encode(audio_response['AudioStream'].read()).decode('utf-8')
    except Exception as e:
        print(f"Polly TTS error: {str(e)}")
        return None


@app.post("/logic/get_test_with_audio/")
async def logic_get_test_with_audio(request: GetLogicTestRequest):
    """
    Get logic test items with TTS audio narration for each question and options.
    Uses the same voice (nova) as reading comprehension for consistency.
    Audio is cached in Firebase under logic_audio/{grade}/{item_id}.
    """
    verify_child_and_token(request.idToken, request.child_id)

    grade = request.grade
    grade_map = {
        "K-1": GradeLevel.KINDERGARTEN_1,
        "1-2": GradeLevel.GRADE_1_2,
        "2-3": GradeLevel.GRADE_2_3,
        "3-4": GradeLevel.GRADE_3_4,
        "Kindergarten": GradeLevel.KINDERGARTEN_1,
        "First": GradeLevel.GRADE_1_2,
        "Second": GradeLevel.GRADE_2_3,
        "Third": GradeLevel.GRADE_3_4,
    }
    grade_level = grade_map.get(grade)
    if not grade_level:
        raise HTTPException(status_code=400, detail=f"Invalid grade: {grade}")

    items = get_items_by_grade(grade_level)

    # Batch read all cached audio from Firebase in 1 call
    all_cached = db_ref.child(f"logic_audio/{grade}").get() or {}

    # Identify which items need audio generation
    items_to_generate = []
    for item in items:
        if item.item_id not in all_cached or not all_cached[item.item_id].get("question_audio"):
            items_to_generate.append(item)

    # Generate audio in parallel for all uncached items, then cache
    if items_to_generate:
        async def gen_item_audio(item):
            question_audio = await generate_tts_audio(item.question_text)
            opt_audios = await asyncio.gather(
                *[generate_tts_audio(opt.text) for opt in item.options]
            )
            return item.item_id, question_audio, list(opt_audios)

        generated = await asyncio.gather(*[gen_item_audio(item) for item in items_to_generate])
        for item_id, q_audio, o_audios in generated:
            if q_audio:
                db_ref.child(f"logic_audio/{grade}/{item_id}").set({
                    "question_audio": q_audio,
                    "option_audios": o_audios,
                    "voice": "nova",
                    "generated_at": datetime.utcnow().isoformat(),
                })
                all_cached[item_id] = {"question_audio": q_audio, "option_audios": o_audios}

    # Build response from cache
    formatted_items = []
    for item in items:
        cached = all_cached.get(item.item_id, {})
        question_audio = cached.get("question_audio")
        option_audios = cached.get("option_audios", [])
        audio_source = "cached" if item.item_id in all_cached else "not_cached"

        fmt = {
            "item_id": item.item_id,
            "item_number": item.item_number,
            "item_type": item.item_type,
            "question_text": item.question_text,
            "difficulty": item.difficulty,
            "question_audio_base64": question_audio,
            "audio_source": audio_source,
            "options": [
                {
                    "index": opt.index,
                    "text": opt.text,
                    "image_url": opt.image_url,
                    "audio_base64": option_audios[i] if i < len(option_audios) else None,
                }
                for i, opt in enumerate(item.options)
            ],
        }

        # Include sort config if present
        if item.sort_config:
            fmt["sort_config"] = {
                "cards": item.sort_config.cards,
                "rounds": [
                    {
                        "round_number": r.round_number,
                        "sort_rule": r.sort_rule,
                        "num_bins": r.num_bins,
                        "rule_shown": r.rule_shown,
                    }
                    for r in item.sort_config.rounds
                ],
            }

        formatted_items.append(fmt)

    return {
        "success": True,
        "test_id": str(uuid.uuid4()),
        "grade": grade,
        "total_items": len(items),
        "instructions": (
            "Listen to each question carefully, then choose your answer. "
            "Think about patterns, relationships, and rules. Take your time!"
        ),
        "items": formatted_items,
    }


@app.post("/admin/pregenerate_logic_audio/")
async def pregenerate_logic_audio(request: GetDetailsRequest):
    """
    Admin endpoint to pre-generate all logic test audio and save to Firebase.
    Same pattern as /admin/pregenerate_story_audio/ for comprehension.
    Call once after deploying new items to cache all audio.
    """
    try:
        decoded = auth.verify_id_token(request.idToken)
        uid = decoded["uid"]
        user_data = db_ref.child("users").child(uid).get()
        if not user_data or not user_data.get("isAdmin", False):
            raise HTTPException(status_code=403, detail="Admin access required")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")

    grade_map = {
        "K-1": GradeLevel.KINDERGARTEN_1,
        "1-2": GradeLevel.GRADE_1_2,
        "2-3": GradeLevel.GRADE_2_3,
        "3-4": GradeLevel.GRADE_3_4,
    }

    results = {"generated": [], "failed": [], "skipped": []}

    for grade_str, grade_level in grade_map.items():
        items = get_items_by_grade(grade_level)
        for item in items:
            # Check if already cached
            cached = db_ref.child(f"logic_audio/{grade_str}/{item.item_id}").get()
            if cached and cached.get("question_audio"):
                results["skipped"].append(f"{grade_str}/{item.item_id}")
                continue

            # Generate question audio
            question_audio = await generate_tts_audio(item.question_text)
            if not question_audio:
                results["failed"].append(f"{grade_str}/{item.item_id}")
                continue

            # Generate option audio
            option_audios = []
            for opt in item.options:
                opt_audio = await generate_tts_audio(opt.text)
                option_audios.append(opt_audio)

            # Save to Firebase
            db_ref.child(f"logic_audio/{grade_str}/{item.item_id}").set({
                "question_audio": question_audio,
                "option_audios": option_audios,
                "voice": "nova",
                "generated_at": datetime.utcnow().isoformat(),
            })
            results["generated"].append(f"{grade_str}/{item.item_id}")

    return {
        "success": True,
        "message": "Logic audio pre-generation complete",
        "results": results,
    }


@app.post("/logic/submit_response/")
async def logic_submit_response(request: SubmitLogicResponseRequest):
    verify_child_and_token(request.idToken, request.child_id)
    result = score_logic_item_response(
        student_id=request.child_id,
        item_id=request.item_id,
        selected_answer_index=request.selected_answer_index,
        response_time_seconds=request.response_time_seconds,
        attempts=request.attempts,
        self_corrected=request.self_corrected,
        explanation_provided=request.explanation_provided,
    )
    return {"success": True, **result}


@app.post("/logic/submit_test/")
async def logic_submit_test(request: SubmitLogicTestRequest):
    user_id, _ = verify_child_and_token(request.idToken, request.child_id)
    result = aggregate_logic_test_results(
        student_id=request.child_id,
        grade=request.grade,
        responses=request.responses,
    )

    # Dear Parent Phase 2: compute tags from raw responses
    items_lookup = {
        item.item_id: {
            "item_number": item.item_number,
            "correct_answer_index": item.correct_answer_index,
            "expected_latency_seconds": item.expected_latency_seconds,
            "item_type": item.item_type,
            "difficulty": item.difficulty,
            "primary_tag": str(item.primary_tag.value),
            "conditional_tags": {k: v.value for k, v in item.conditional_tags.items()},
        }
        for item in ALL_LOGIC_ITEMS
    }
    dear_parent_tags = tag_logic_test(request.responses, items_lookup)
    per_item_tags = tag_logic_per_item(request.responses, items_lookup)

    score_id = db_ref.child(f"users/{user_id}/children/{request.child_id}/logic_tests").push().key
    score_data = {
        "grade": request.grade,
        "score": result["score"],
        "percentage": result["percentage"],
        "correct_answers": result["correct_answers"],
        "total_items": result["total_items"],
        "level": result["level"],
        "cognitive_tags": result["cognitive_tags"],
        "tag_outputs": result.get("tag_outputs", []),
        "tag_breakdown": result["tag_breakdown"],
        "reasoning_under_load_detected": result["reasoning_under_load_detected"],
        "trial_and_error_detected": result["trial_and_error_detected"],
        "strategy_shift_difficulty_detected": result["strategy_shift_difficulty_detected"],
        "impulsive_response_detected": result.get("impulsive_response_detected", False),
        "self_correction_detected": result.get("self_correction_detected", False),
        "cognitive_flexibility_intact": result.get("cognitive_flexibility_intact", False),
        "flexible_strategy_use_detected": result.get("flexible_strategy_use_detected", False),
        "dear_parent_tags": dear_parent_tags,
        "per_item_tags": per_item_tags,
        "message": result["message"],
        "timestamp": datetime.utcnow().isoformat(),
        "responses": request.responses,
    }
    db_ref.child(f"users/{user_id}/children/{request.child_id}/logic_tests/{score_id}").set(sanitize_firebase_data(score_data))

    result["score_id"] = score_id
    result["dear_parent_tags"] = dear_parent_tags
    result["per_item_tags"] = per_item_tags
    return {"success": True, **result}


@app.post("/logic/complete_result/")
async def logic_complete_result(request: CompleteLogicResultRequest):
    user_id, _ = verify_child_and_token(request.idToken, request.child_id)

    # Query logic_tests path (like speaking uses speaking_tests)
    logic_data = db_ref.child(f"users/{user_id}/children/{request.child_id}/logic_tests").get() or {}

    # Filter by grade and sort by timestamp
    filtered = []
    for test_id, s in logic_data.items():
        if request.grade and s.get("grade") != request.grade:
            continue
        filtered.append((s.get("timestamp", ""), s))

    if not filtered:
        raise HTTPException(
            status_code=404,
            detail=f"No logic test results found for child {request.child_id}" + (f" in grade {request.grade}" if request.grade else "")
        )

    # Get the latest logic result
    filtered.sort(key=lambda x: x[0], reverse=True)
    _, latest_score = filtered[0]

    return build_complete_logic_result(
        request.child_id, request.grade, score_data=latest_score
    )


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

    # Dear Parent Phase 2: compute spelling tags
    dear_parent_tags = tag_spelling_test(results, grade)
    per_word_tags = tag_spelling_per_word(results)

    score_id = db_ref.child(f"users/{user_id}/children/{request.child_id}/scores").push().key
    score_data = {
        "grade": grade,
        "evaluation": evaluation,
        "assessment_summary": sanitize_firebase_data(assessment_summary),
        "error_analysis": sanitize_firebase_data(error_counts),
        "instructional_recommendation": recommendation,
        "dear_parent_tags": dear_parent_tags,
        "per_word_tags": per_word_tags,
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
        "instructional_recommendation": recommendation,
        "dear_parent_tags": dear_parent_tags,
        "per_word_tags": per_word_tags
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
        # Read from Firebase cache, generate + cache if missing
        cached = db_ref.child(f"spelling_audio/_all/{word}").get()
        if cached and cached.get("word_audio"):
            return {"base64_audio": cached["word_audio"]}
        word_base64 = await generate_tts_audio(word, speed=0.9)
        if word_base64:
            db_ref.child(f"spelling_audio/_all/{word}").set({
                "word_audio": word_base64,
                "voice": "nova",
                "generated_at": datetime.utcnow().isoformat(),
            })
            return {"base64_audio": word_base64}
        return {"base64_audio": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get audio: {str(e)}")

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
        # Batch read all cached audio from Firebase in 1 call
        all_cached = db_ref.child(f"spelling_audio/{grade}").get() or {}

        # Identify which words need audio generation
        words_to_generate = []
        for item in shuffled_words:
            word = item["word"]
            if word not in all_cached or not all_cached[word].get("word_audio"):
                words_to_generate.append(item)

        # Generate audio in parallel for all uncached words, then cache
        if words_to_generate:
            async def gen_word_audio(item):
                word = item["word"]
                sentence = item["sentence"]
                word_base64 = await generate_tts_audio(word, speed=0.95)
                sentence_base64 = await generate_tts_audio(sentence, speed=1.0)
                return word, word_base64, sentence_base64

            generated = await asyncio.gather(*[gen_word_audio(i) for i in words_to_generate])
            for word, w_b64, s_b64 in generated:
                if w_b64:
                    db_ref.child(f"spelling_audio/{grade}/{word}").set({
                        "word_audio": w_b64,
                        "sentence_audio": s_b64,
                        "voice": "nova",
                        "generated_at": datetime.utcnow().isoformat(),
                    })
                    all_cached[word] = {"word_audio": w_b64, "sentence_audio": s_b64}

        # Build response from cache
        for item in shuffled_words:
            word = item["word"]
            sentence = item["sentence"]
            word_type = item["type"]
            cached = all_cached.get(word, {})
            word_base64 = cached.get("word_audio")
            sentence_base64 = cached.get("sentence_audio")

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
            "dear_parent_tags": latest.get("dear_parent_tags", []),
            "per_word_tags": latest.get("per_word_tags", []),
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
        "dear_parent_tags": latest.get("dear_parent_tags", []),
        "per_word_tags": latest.get("per_word_tags", []),
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
    
    # Get sentence from DB cache, generate + cache if missing
    selected = sentences[0]
    cached = db_ref.child(f"speaking_audio/{grade}/{selected['id']}").get() or {}
    audio_base64 = cached.get("audio_base64")
    if not audio_base64:
        audio_base64 = await generate_tts_audio(selected["sentence"], speed=0.9)
        if audio_base64:
            db_ref.child(f"speaking_audio/{grade}/{selected['id']}").set({
                "audio_base64": audio_base64,
                "voice": "nova",
                "generated_at": datetime.utcnow().isoformat(),
            })
    
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
    """Get all sentences for a speaking test with audio (from DB cache only)."""
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
    
    # Read all cached audio from Firebase in 1 call
    all_cached = db_ref.child(f"speaking_audio/{grade}").get() or {}
    
    # Identify which sentences need audio generation
    sents_to_generate = []
    for sent in sentences:
        sid = sent["id"]
        if sid not in all_cached or not all_cached[sid].get("audio_base64"):
            sents_to_generate.append(sent)
    
    # Generate audio in parallel for all uncached sentences, then cache
    if sents_to_generate:
        async def gen_sent_audio(sent):
            audio = await generate_tts_audio(sent["sentence"], speed=0.9)
            return sent["id"], audio
        
        generated = await asyncio.gather(*[gen_sent_audio(s) for s in sents_to_generate])
        for sid, audio_b64 in generated:
            if audio_b64:
                db_ref.child(f"speaking_audio/{grade}/{sid}").set({
                    "audio_base64": audio_b64,
                    "voice": "nova",
                    "generated_at": datetime.utcnow().isoformat(),
                })
                all_cached[sid] = {"audio_base64": audio_b64}
    
    # Build response from cache
    result_sentences = []
    for sent in sentences:
        cached = all_cached.get(sent["id"], {})
        result_sentences.append({
            "sentence_id": sent["id"],
            "sentence": sent["sentence"],
            "word_count": sent["word_count"],
            "difficulty": sent["difficulty"],
            "audio_base64": cached.get("audio_base64")
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

    # Dear Parent Phase 2: compute speaking tags
    # Enrich results with difficulty from sentence bank for the tagger
    tagging_results = []
    for r in results:
        enriched = dict(r)
        sid = r.get("sentence_id", "")
        if sid in sentence_map:
            enriched["difficulty"] = sentence_map[sid].get("difficulty", "medium")
        tagging_results.append(enriched)
    dear_parent_tags = tag_speaking_test(tagging_results)
    per_sentence_tags = tag_speaking_per_sentence(tagging_results)

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
        "dear_parent_tags": dear_parent_tags,
        "per_sentence_tags": per_sentence_tags,
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
        "dear_parent_tags": dear_parent_tags,
        "per_sentence_tags": per_sentence_tags,
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
        "dear_parent_tags": latest_test.get("dear_parent_tags", []),
        "per_sentence_tags": latest_test.get("per_sentence_tags", []),
        "all_results": all_results
    }


# ==================== READING COMPREHENSION APIs ====================

async def generate_story_audio_openai(story_text: str, voice: str = "nova") -> str:
    """
    Generate expressive story narration using OpenAI TTS.
    Now uses the shared generate_tts_audio function for consistency.
    Falls back to AWS Polly if OpenAI is unavailable.
    """
    return await generate_tts_audio(story_text, voice=voice, speed=0.85)


@app.post("/admin/pregenerate_speaking_audio/")
async def pregenerate_speaking_audio(request: GetDetailsRequest):
    """
    Admin endpoint to pre-generate all speaking sentence audio and save to Firebase.
    Call once after deploying to cache all audio so /speaking/get_all_sentences/ is instant.
    Same pattern as /admin/pregenerate_story_audio/ and /admin/pregenerate_logic_audio/.
    """
    try:
        decoded = auth.verify_id_token(request.idToken)
        uid = decoded["uid"]
        user_data = db_ref.child("users").child(uid).get()
        if not user_data or not user_data.get("isAdmin", False):
            raise HTTPException(status_code=403, detail="Admin access required")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")

    results = {"generated": [], "failed": [], "skipped": []}

    for grade, sentences in speaking_sentences.items():
        # Batch check existing cache
        existing = db_ref.child(f"speaking_audio/{grade}").get() or {}

        sents_to_gen = []
        for sent in sentences:
            sid = sent["id"]
            if sid in existing and existing[sid].get("audio_base64"):
                results["skipped"].append(f"{grade}/{sid}")
            else:
                sents_to_gen.append(sent)

        if not sents_to_gen:
            continue

        # Generate in parallel (max 8 at a time)
        async def gen_one(sent):
            audio = await generate_tts_audio(sent["sentence"], voice="nova", speed=0.9)
            return sent["id"], audio

        generated = await asyncio.gather(*[gen_one(s) for s in sents_to_gen])

        for sid, audio_b64 in generated:
            if audio_b64:
                db_ref.child(f"speaking_audio/{grade}/{sid}").set({
                    "audio_base64": audio_b64,
                    "voice": "nova",
                    "generated_at": datetime.utcnow().isoformat(),
                })
                results["generated"].append(f"{grade}/{sid}")
            else:
                results["failed"].append(f"{grade}/{sid}")

    return {
        "success": True,
        "message": "Speaking audio pre-generation complete",
        "results": results
    }


@app.post("/admin/pregenerate_spelling_audio/")
async def pregenerate_spelling_audio(request: GetDetailsRequest):
    """
    Admin endpoint to pre-generate all spelling word + sentence audio and save to Firebase.
    Call once after deploying to cache all audio so /generate_all_grade_audio/ is instant.
    """
    try:
        decoded = auth.verify_id_token(request.idToken)
        uid = decoded["uid"]
        user_data = db_ref.child("users").child(uid).get()
        if not user_data or not user_data.get("isAdmin", False):
            raise HTTPException(status_code=403, detail="Admin access required")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")

    results = {"generated": [], "failed": [], "skipped": []}

    for grade in word_lists:
        words = _audio_words_for_grade(grade)
        if not words:
            continue

        existing = db_ref.child(f"spelling_audio/{grade}").get() or {}

        words_to_gen = []
        for item in words:
            word = item["word"]
            if word in existing and existing[word].get("word_audio"):
                results["skipped"].append(f"{grade}/{word}")
            else:
                words_to_gen.append(item)

        if not words_to_gen:
            continue

        async def gen_word(item):
            w = item["word"]
            s = item["sentence"]
            w_b64 = await generate_tts_audio(w, speed=0.95)
            s_b64 = await generate_tts_audio(s, speed=1.0)
            return w, w_b64, s_b64

        generated = await asyncio.gather(*[gen_word(i) for i in words_to_gen])

        for word, w_b64, s_b64 in generated:
            if w_b64:
                db_ref.child(f"spelling_audio/{grade}/{word}").set({
                    "word_audio": w_b64,
                    "sentence_audio": s_b64,
                    "voice": "nova",
                    "generated_at": datetime.utcnow().isoformat(),
                })
                results["generated"].append(f"{grade}/{word}")
            else:
                results["failed"].append(f"{grade}/{word}")

    return {
        "success": True,
        "message": "Spelling audio pre-generation complete",
        "results": results
    }


@app.post("/admin/pregenerate_story_audio/")
async def pregenerate_story_audio(request: GetDetailsRequest):
    """
    Admin endpoint to pre-generate all story audio and save to Firebase.
    This should be called once to cache all audio.
    """
    try:
        decoded = auth.verify_id_token(request.idToken)
        uid = decoded["uid"]
        user_data = db_ref.child("users").child(uid).get()
        if not user_data or not user_data.get("isAdmin", False):
            raise HTTPException(status_code=403, detail="Admin access required")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
    
    results = {"generated": [], "failed": [], "skipped": []}
    
    for grade, stories in comprehension_stories.items():
        for story in stories:
            story_id = story["id"]
            
            # Check if already cached
            cached = db_ref.child(f"story_audio/{grade}/{story_id}").get()
            if cached and cached.get("audio_base64"):
                results["skipped"].append(f"{grade}/{story_id}")
                continue
            
            # Generate audio
            audio_base64 = await generate_story_audio_openai(story["story"], voice="nova")
            
            if audio_base64:
                # Save to Firebase
                db_ref.child(f"story_audio/{grade}/{story_id}").set({
                    "audio_base64": audio_base64,
                    "title": story["title"],
                    "voice": "nova",
                    "generated_at": datetime.utcnow().isoformat()
                })
                results["generated"].append(f"{grade}/{story_id}")
            else:
                results["failed"].append(f"{grade}/{story_id}")
    
    return {
        "success": True,
        "message": "Audio pre-generation complete",
        "results": results
    }


@app.post("/admin/regenerate_story_audio/")
async def regenerate_story_audio(request: GetDetailsRequest, grade: str = None, story_id: str = None):
    """
    Admin endpoint to regenerate specific story audio or all.
    """
    try:
        decoded = auth.verify_id_token(request.idToken)
        uid = decoded["uid"]
        user_data = db_ref.child("users").child(uid).get()
        if not user_data or not user_data.get("isAdmin", False):
            raise HTTPException(status_code=403, detail="Admin access required")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
    
    results = {"regenerated": [], "failed": []}
    
    # Determine which stories to regenerate
    if grade and story_id:
        # Specific story
        story = next((s for s in comprehension_stories.get(grade, []) if s["id"] == story_id), None)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        stories_to_process = [(grade, story)]
    elif grade:
        # All stories in a grade
        stories_to_process = [(grade, s) for s in comprehension_stories.get(grade, [])]
    else:
        # All stories
        stories_to_process = [(g, s) for g, stories in comprehension_stories.items() for s in stories]
    
    for g, story in stories_to_process:
        audio_base64 = await generate_story_audio_openai(story["story"], voice="nova")
        if audio_base64:
            db_ref.child(f"story_audio/{g}/{story['id']}").set({
                "audio_base64": audio_base64,
                "title": story["title"],
                "voice": "nova",
                "generated_at": datetime.utcnow().isoformat()
            })
            results["regenerated"].append(f"{g}/{story['id']}")
        else:
            results["failed"].append(f"{g}/{story['id']}")
    
    return {"success": True, "results": results}


@app.post("/comprehension/get_stories/")
async def get_comprehension_stories(request: ComprehensionGetRequest):
    """
    Get 2 stories with audio and questions for the specified grade.
    Reads pre-generated audio from Firebase cache only — no real-time generation.
    """
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
    if grade not in comprehension_stories:
        raise HTTPException(status_code=400, detail="Invalid grade. Must be: Kindergarten, First, Second, or Third")
    
    # Get stories for the grade
    stories = comprehension_stories[grade]
    
    # Batch read all cached audio from Firebase in 1 call
    all_cached = db_ref.child(f"story_audio/{grade}").get() or {}
    
    # Identify which stories need audio generation
    stories_to_generate = []
    for story in stories:
        sid = story["id"]
        if sid not in all_cached or not all_cached[sid].get("audio_base64"):
            stories_to_generate.append(story)
    
    # Generate audio in parallel for uncached stories, then cache
    if stories_to_generate:
        async def gen_story_audio(story):
            audio = await generate_story_audio_openai(story["story"], voice="nova")
            return story["id"], audio
        generated = await asyncio.gather(*[gen_story_audio(s) for s in stories_to_generate])
        for sid, audio_b64 in generated:
            if audio_b64:
                story_obj = next(s for s in stories if s["id"] == sid)
                db_ref.child(f"story_audio/{grade}/{sid}").set({
                    "audio_base64": audio_b64,
                    "title": story_obj["title"],
                    "voice": "nova",
                    "generated_at": datetime.utcnow().isoformat()
                })
                all_cached[sid] = {"audio_base64": audio_b64, "title": story_obj["title"]}
    
    # Build response from cache
    result_stories = []
    for story in stories:
        story_id = story["id"]
        cached = all_cached.get(story_id, {})
        story_audio_base64 = cached.get("audio_base64")
        audio_source = "cached_openai" if story_id in all_cached and cached.get("audio_base64") else "failed"
        
        if not story_audio_base64:
            audio_source = "failed"
        
        # Prepare questions (without correct_index for client)
        questions_for_client = []
        for q in story["questions"]:
            questions_for_client.append({
                "id": q["id"],
                "question": q["question"],
                "options": q["options"]
                # Note: correct_index is NOT sent to client
            })
        
        result_stories.append({
            "story_id": story["id"],
            "title": story["title"],
            "story_text": story["story"],
            "story_audio_base64": story_audio_base64,
            "audio_source": audio_source,
            "duration_estimate": story.get("duration_estimate", "60 seconds"),
            "questions": questions_for_client,
            "total_questions": len(questions_for_client)
        })
    
    return {
        "grade": grade,
        "total_stories": len(result_stories),
        "total_questions": sum(s["total_questions"] for s in result_stories),
        "instructions": "Listen to each story carefully, then answer the questions. Each question has 4 options.",
        "stories": result_stories
    }


@app.post("/comprehension/submit/")
async def submit_comprehension_test(request: ComprehensionSubmitRequest):
    """
    Submit answers for the reading comprehension test.
    Calculates score and saves results to Firebase.
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
    if grade not in comprehension_stories:
        raise HTTPException(status_code=400, detail="Invalid grade")
    
    # Get the correct answers from our data
    stories_data = comprehension_stories[grade]
    story_map = {s["id"]: s for s in stories_data}
    
    # Build question answer key
    answer_key = {}
    for story in stories_data:
        for q in story["questions"]:
            answer_key[q["id"]] = {
                "correct_index": q["correct_index"],
                "correct_answer": q["options"][q["correct_index"]],
                "question": q["question"],
                "options": q["options"],
                "story_id": story["id"],
                "story_title": story["title"]
            }
    
    # Process submitted answers
    results = []
    total_correct = 0
    total_questions = 0
    
    for story_answer in request.story_answers:
        story_id = story_answer.story_id
        story_info = story_map.get(story_id, {})
        story_title = story_info.get("title", "Unknown Story")
        
        story_results = {
            "story_id": story_id,
            "story_title": story_title,
            "questions": []
        }
        
        for qa in story_answer.answers:
            question_id = qa.question_id
            selected_index = qa.selected_index
            
            if question_id in answer_key:
                key = answer_key[question_id]
                is_correct = selected_index == key["correct_index"]
                
                if is_correct:
                    total_correct += 1
                total_questions += 1
                
                story_results["questions"].append({
                    "question_id": question_id,
                    "question": key["question"],
                    "selected_index": selected_index,
                    "selected_answer": key["options"][selected_index] if 0 <= selected_index < len(key["options"]) else "Invalid",
                    "correct_index": key["correct_index"],
                    "correct_answer": key["correct_answer"],
                    "is_correct": is_correct
                })
            else:
                # Question not found
                total_questions += 1
                story_results["questions"].append({
                    "question_id": question_id,
                    "question": "Unknown question",
                    "selected_index": selected_index,
                    "selected_answer": "Unknown",
                    "correct_index": -1,
                    "correct_answer": "Unknown",
                    "is_correct": False
                })
        
        results.append(story_results)
    
    # Calculate overall metrics
    max_score = len(answer_key)  # Total possible questions (8 for 2 stories × 4 questions)
    percentage = round((total_correct / max_score) * 100, 1) if max_score > 0 else 0
    
    # Determine level
    if percentage >= 90:
        level = "Excellent Reader"
        status = "Above"
    elif percentage >= 75:
        level = "Good Reader"
        status = "At"
    elif percentage >= 50:
        level = "Developing Reader"
        status = "Below"
    else:
        level = "Needs Practice"
        status = "Below"
    
    # Generate recommendation
    if percentage >= 90:
        recommendation = f"Outstanding comprehension! Consider advancing to more challenging texts."
    elif percentage >= 75:
        recommendation = f"Good understanding of the stories. Continue practicing with varied reading materials."
    elif percentage >= 50:
        recommendation = f"Keep practicing! Try re-reading stories and discussing them with an adult."
    else:
        recommendation = f"Focus on listening carefully to stories. Practice summarizing what happened after each story."
    
    # Dear Parent Phase 2: compute comprehension tags
    dear_parent_tags = tag_comprehension_test(results, COMPREHENSION_QUESTION_TYPES)
    per_question_tags = tag_comprehension_per_question(results, COMPREHENSION_QUESTION_TYPES)

    # Save to Firebase
    test_id = db_ref.child(f"users/{user_id}/children/{request.child_id}/comprehension_tests").push().key
    test_data = {
        "grade": grade,
        "results": results,
        "total_questions": max_score,
        "correct_answers": total_correct,
        "score": total_correct,
        "max_score": max_score,
        "percentage": percentage,
        "level": level,
        "status": status,
        "recommendation": recommendation,
        "dear_parent_tags": dear_parent_tags,
        "per_question_tags": per_question_tags,
        "timestamp": datetime.utcnow().isoformat()
    }
    db_ref.child(f"users/{user_id}/children/{request.child_id}/comprehension_tests/{test_id}").set(test_data)
    
    return {
        "success": True,
        "user_id": user_id,
        "child_id": request.child_id,
        "grade": grade,
        "test_id": test_id,
        "total_questions": max_score,
        "correct_answers": total_correct,
        "score": total_correct,
        "max_score": max_score,
        "percentage": percentage,
        "level": level,
        "status": status,
        "recommendation": recommendation,
        "results": results,
        "dear_parent_tags": dear_parent_tags,
        "per_question_tags": per_question_tags,
        "message": f"Test completed: {total_correct}/{max_score} correct ({percentage}%)"
    }


@app.post("/comprehension/complete_result/")
async def comprehension_complete_result(request: ComprehensionResultRequest):
    """
    Get complete reading comprehension test results for a child.
    Returns the latest test result with detailed breakdown.
    """
    try:
        decoded_token = auth.verify_id_token(request.idToken)
        user_id = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    child_data = db_ref.child(f"users/{user_id}/children/{request.child_id}").get()
    if not child_data:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Fetch all comprehension tests for the child
    tests_data = db_ref.child(f"users/{user_id}/children/{request.child_id}/comprehension_tests").get() or {}
    if not tests_data:
        raise HTTPException(status_code=404, detail="No comprehension test results found")
    
    # Filter by grade if specified
    filtered = []
    for test_id, t in tests_data.items():
        g = t.get("grade")
        if request.grade and g != request.grade:
            continue
        filtered.append((t.get("timestamp", ""), t, test_id))
    
    if not filtered:
        raise HTTPException(status_code=404, detail=f"No comprehension results for grade: {request.grade or 'any'}")
    
    # Sort by timestamp descending (latest first)
    filtered.sort(key=lambda x: x[0], reverse=True)
    latest_test = filtered[0][1]
    
    # Build response
    results = latest_test.get("results", [])
    correct_answers = latest_test.get("correct_answers", 0)
    max_score = latest_test.get("max_score", 8)
    percentage = latest_test.get("percentage", 0)
    level = latest_test.get("level", "Developing Reader")
    status = latest_test.get("status", "Below")
    recommendation = latest_test.get("recommendation", "")
    
    # Determine placement
    if percentage >= 90:
        placement = "Above Grade Level"
        next_step = "Consider more advanced reading materials"
    elif percentage >= 75:
        placement = "At Grade Level"
        next_step = "Continue with current grade level materials"
    else:
        placement = "Below Grade Level"
        next_step = "Practice with guided reading and comprehension activities"
    
    # Calculate per-story breakdown
    story_breakdown = []
    for story_result in results:
        story_correct = sum(1 for q in story_result.get("questions", []) if q.get("is_correct", False))
        story_total = len(story_result.get("questions", []))
        story_pct = round((story_correct / story_total) * 100, 1) if story_total > 0 else 0
        
        story_breakdown.append({
            "story_id": story_result.get("story_id"),
            "story_title": story_result.get("story_title"),
            "correct": story_correct,
            "total": story_total,
            "percentage": story_pct,
            "questions": story_result.get("questions", [])
        })
    
    return {
        "user_id": user_id,
        "child_id": request.child_id,
        "grade": latest_test.get("grade"),
        "test_timestamp": latest_test.get("timestamp"),
        "summary": {
            "total_questions": max_score,
            "correct_answers": correct_answers,
            "percentage": percentage,
            "level": level,
            "status": status
        },
        "parent_summary": {
            "overall_score": f"{correct_answers}/{max_score}",
            "percentage": percentage,
            "level": level,
            "grade_placement": placement,
            "next_step": next_step,
            "recommendation": recommendation,
            "note": "Assessment is instructional and not a clinical diagnosis."
        },
        "story_breakdown": story_breakdown,
        "dear_parent_tags": latest_test.get("dear_parent_tags", []),
        "per_question_tags": latest_test.get("per_question_tags", []),
        "actions": [
            {"label": "Retry Test", "type": "button", "action": "retry_test"},
            {"label": "View Stories", "type": "button", "action": "view_stories"},
            {"label": "Download Report (PDF)", "type": "button", "action": "download_pdf"}
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)