"""
Authentication endpoints for the High School Management System API
"""

from fastapi import APIRouter, HTTPException, Response
from typing import Dict, Any
import os

from ..database import teachers_collection, verify_password

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

# Cookie lifetime and security settings
_SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days in seconds
_SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "false").lower() == "true"


@router.post("/login")
def login(username: str, password: str, response: Response) -> Dict[str, Any]:
    """Login a teacher account"""
    # Find the teacher in the database
    teacher = teachers_collection.find_one({"_id": username})

    # Verify password using Argon2 verifier from database.py
    if not teacher or not verify_password(teacher.get("password", ""), password):
        raise HTTPException(
            status_code=401, detail="Invalid username or password")

    # Set an HttpOnly session cookie so the browser sends it automatically
    response.set_cookie(
        key="session_user",
        value=username,
        httponly=True,
        samesite="strict",
        secure=_SECURE_COOKIES,
        max_age=_SESSION_MAX_AGE,
    )

    # Return teacher information (excluding password)
    return {
        "username": teacher["username"],
        "display_name": teacher["display_name"],
        "role": teacher["role"]
    }


@router.post("/logout")
def logout(response: Response) -> Dict[str, str]:
    """Logout the current teacher, clearing the session cookie"""
    response.delete_cookie(key="session_user", httponly=True, samesite="strict", secure=_SECURE_COOKIES)
    return {"message": "Logged out"}


@router.get("/check-session")
def check_session(username: str) -> Dict[str, Any]:
    """Check if a session is valid by username"""
    teacher = teachers_collection.find_one({"_id": username})

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    return {
        "username": teacher["username"],
        "display_name": teacher["display_name"],
        "role": teacher["role"]
    }
