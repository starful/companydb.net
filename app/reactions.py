"""Like / dislike reactions — same Firestore pattern as okcaddie / jpcampus."""

from __future__ import annotations

import os

import firebase_admin
from firebase_admin import credentials, firestore
from flask import Blueprint, jsonify, request

reactions_bp = Blueprint("reactions", __name__)
COLLECTION_NAME = os.getenv("REACTIONS_COLLECTION", "companydb")

try:
    if not firebase_admin._apps:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    db = firestore.client()
except Exception as e:
    print(f"Firebase initialization error: {e}")
    db = None


def get_client_ip() -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown_ip"


def sync_process_reaction(db_client, collection_name, slug, safe_ip, new_type):
    post_ref = db_client.collection(collection_name).document(slug)
    reaction_ref = post_ref.collection("reactions").document(safe_ip)

    reaction_doc = reaction_ref.get()
    likes_inc, dislikes_inc = 0, 0
    batch = db_client.batch()

    if not reaction_doc.exists:
        if new_type == "like":
            likes_inc = 1
        else:
            dislikes_inc = 1
        batch.set(reaction_ref, {"type": new_type})
        current_type = None
    else:
        current_type = reaction_doc.to_dict().get("type")
        if current_type == new_type:
            if new_type == "like":
                likes_inc = -1
            else:
                dislikes_inc = -1
            batch.delete(reaction_ref)
        else:
            if new_type == "like":
                likes_inc = 1
                dislikes_inc = -1
            else:
                likes_inc = -1
                dislikes_inc = 1
            batch.update(reaction_ref, {"type": new_type})

    batch.set(
        post_ref,
        {
            "likes_count": firestore.Increment(likes_inc),
            "dislikes_count": firestore.Increment(dislikes_inc),
        },
        merge=True,
    )
    batch.commit()
    action_result = "added" if (not reaction_doc.exists) or current_type != new_type else "removed"
    updated_doc = post_ref.get()
    return action_result, updated_doc.to_dict() or {}


@reactions_bp.get("/api/reactions/<slug>")
def get_reactions(slug: str):
    if db is None:
        return jsonify({"likes": 0, "dislikes": 0, "error": "Database not connected"})
    try:
        doc_ref = db.collection(COLLECTION_NAME).document(slug)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            return jsonify(
                {
                    "likes": data.get("likes_count", 0),
                    "dislikes": data.get("dislikes_count", 0),
                }
            )
    except Exception as e:
        print(f"Read Error: {e}")
    return jsonify({"likes": 0, "dislikes": 0})


@reactions_bp.post("/api/like/<slug>")
def like_post(slug: str):
    return _process_reaction(slug, "like")


@reactions_bp.post("/api/dislike/<slug>")
def dislike_post(slug: str):
    return _process_reaction(slug, "dislike")


def _process_reaction(slug: str, reaction_type: str):
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500

    safe_ip = get_client_ip().replace(".", "_").replace(":", "_")
    try:
        result, data = sync_process_reaction(
            db, COLLECTION_NAME, slug, safe_ip, reaction_type
        )
    except Exception:
        return jsonify({"error": "Reaction processing failed"}), 500

    return jsonify(
        {
            "status": "success",
            "action": result,
            "likes": data.get("likes_count", 0),
            "dislikes": data.get("dislikes_count", 0),
            "current_type": reaction_type if result == "added" else None,
        }
    )
