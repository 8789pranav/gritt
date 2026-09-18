"""One-off: what does Pk's evidence actually support? Read-only."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.snapshot_service import SnapshotService
from app.services.snapshot_writer import SnapshotWriter

CHILD = "242cfda1-9b36-4d0b-bf5b-e930c086e435"

from firebase_admin import auth as firebase_auth
from app.infrastructure.firebase import get_firebase_client

client = get_firebase_client()
uid = firebase_auth.get_user_by_email("rajdandeepak@gmail.com").uid
child = client.ref(f"users/{uid}/children/{CHILD}").get()

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

svc = SnapshotService()
grade = child.get("grade")
evidence = svc.build_evidence(
    "", CHILD, grade, uid=uid, child_data=child
)
print("grade used          :", grade)

print("strengths            :", len(evidence.get("strengths") or []))
print("kept_at_it           :", evidence.get("kept_at_it"))
from app.services.snapshot_writer import _growing_plan
print("growing plan:")
for g in _growing_plan(evidence):
    print("  -", g["cluster"]["area_display_name"], g["signals"])

print("\ncalling the writer with real evidence...")
letter = SnapshotWriter().write(evidence)
meta = letter.get("meta") or {}
print("\nllm_generated :", meta.get("llm_generated"))
print("voice slips   :", meta.get("voice_slips"))
print("noticed items :", len(letter.get("what_i_noticed") or []))
print("growing items :", len(letter.get("still_growing") or []))
