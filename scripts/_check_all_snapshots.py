"""One-off: which children have a cached letter, and does it have a noticed section?"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firebase_admin import auth as firebase_auth
from app.infrastructure.firebase import get_firebase_client

client = get_firebase_client()
uid = firebase_auth.get_user_by_email("rajdandeepak@gmail.com").uid

children = client.ref(f"users/{uid}/children").get() or {}
for child_id, child in children.items():
    name = (child or {}).get("name", "?")
    saved = client.ref(f"users/{uid}/children/{child_id}/snapshot").get()
    if not saved:
        print(f"{name:12} no cached letter")
        continue
    letter = saved.get("snapshot") or {}
    meta = letter.get("meta") or {}
    noticed = letter.get("what_i_noticed") or letter.get("noticed") or []
    growing = letter.get("still_growing") or letter.get("growing") or []
    print(
        f"{name:12} noticed={len(noticed)} growing={len(growing)} "
        f"llm={meta.get('llm_generated')} model={meta.get('model')} "
        f"prompt_version={meta.get('prompt_version') or 'old'}"
    )
