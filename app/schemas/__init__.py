"""Pydantic request/response schemas (DTOs) for every API endpoint."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Auth & account
# ---------------------------------------------------------------------------
class GradeInput(BaseModel):
    grade: str


class UserCreate(BaseModel):
    idToken: str
    email: str
    name: str
    password: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserDetails(BaseModel):
    idToken: str
    email: str
    name: str
    age: int


class GetDetailsRequest(BaseModel):
    idToken: str


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
    scores: List[Dict[str, Any]] = []


class MakeAdminRequest(BaseModel):
    idToken: str
    targetEmail: str


class SetBypassPaymentRequest(BaseModel):
    idToken: str
    enabled: bool


class CompleteResultRequest(BaseModel):
    idToken: str
    child_id: str
    grade: Optional[str] = None


# ---------------------------------------------------------------------------
# Spelling
# ---------------------------------------------------------------------------
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


class AudioRequest(BaseModel):
    idToken: str
    text: str


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
class FeedbackRequest(BaseModel):
    """The live form asks q13-q15 only; q1-q12 are kept for older clients."""

    idToken: str
    child_id: str
    q1_grade: Optional[str] = ""
    q2_prior_assessments: Optional[str] = ""
    q3_spelling_confidence: Optional[str] = ""
    q4_assessment_length: Optional[str] = ""
    q5_difficulty_level: Optional[str] = ""
    q6_engagement_level: Optional[str] = ""
    q7_technical_issues: Optional[str] = ""
    q8_results_clarity: Optional[str] = ""
    q9_recommendations_helpful: Optional[str] = ""
    q10_information_amount: Optional[str] = ""
    q11_overall_satisfaction: Optional[str] = ""
    q12_comments: Optional[str] = ""
    q13_sounded_like_child: Optional[str] = ""
    q14_new_information: Optional[str] = ""
    q15_show_to_teacher: Optional[str] = ""


# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------
class GetLogicTestRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str


class SubmitLogicResponseRequest(BaseModel):
    idToken: str
    child_id: str
    item_id: str
    selected_answer_index: int
    response_time_seconds: float = 0.0
    attempts: int = 1
    self_corrected: bool = False
    explanation_provided: Optional[str] = None


class LogicResponseItem(BaseModel):
    item_id: str
    selected_answer_index: int
    response_time_seconds: float = 0.0
    attempts: int = 1
    self_corrected: bool = False
    explanation_provided: Optional[str] = None


class SubmitLogicTestRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str
    responses: List[LogicResponseItem]


class CompleteLogicResultRequest(BaseModel):
    idToken: str
    child_id: str
    grade: Optional[str] = None


# ---------------------------------------------------------------------------
# Speaking
# ---------------------------------------------------------------------------
class SpeakingSentenceRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str


class SpeakingAnalyzeRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str
    original_sentence: str
    audio_base64: str
    audio_format: str = "mp3"


class SpeakingSubmissionItem(BaseModel):
    sentence_id: str
    original_sentence: str
    audio_base64: str
    audio_format: str = "mp3"


class SpeakingSubmitRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str
    sentence_id: Optional[str] = None
    original_sentence: Optional[str] = None
    audio_base64: Optional[str] = None
    audio_format: Optional[str] = "mp3"
    submissions: Optional[List[SpeakingSubmissionItem]] = None


class SpeakingResultRequest(BaseModel):
    idToken: str
    child_id: str
    grade: Optional[str] = None


# ---------------------------------------------------------------------------
# Comprehension
# ---------------------------------------------------------------------------
class ComprehensionQuestionAnswer(BaseModel):
    question_id: str
    selected_index: int


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
    grade: Optional[str] = None


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
class PaymentQuoteRequest(BaseModel):
    idToken: str
    child_ids: List[str]


class CreateCheckoutSessionRequest(BaseModel):
    idToken: str
    child_ids: List[str]
    success_url: str
    cancel_url: str


class PaymentStatusRequest(BaseModel):
    idToken: str
    payment_id: Optional[str] = None
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Final Report
# ---------------------------------------------------------------------------
class FinalReportRequest(BaseModel):
    idToken: str
    child_id: str
    grade: str
