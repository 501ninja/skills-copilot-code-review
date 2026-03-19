"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=1, max_length=2000)
    expires_at: str = Field(..., description="Expiration date in YYYY-MM-DD format")
    starts_at: Optional[str] = Field(None, description="Optional start date in YYYY-MM-DD format")


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    message: Optional[str] = Field(None, min_length=1, max_length=2000)
    expires_at: Optional[str] = Field(None, description="Expiration date in YYYY-MM-DD format")
    starts_at: Optional[str] = Field(None, description="Optional start date in YYYY-MM-DD format")


def parse_iso_date(label: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}. Use YYYY-MM-DD format."
        ) from exc


def ensure_valid_date_window(starts_at: Optional[str], expires_at: str) -> Optional[str]:
    """Validate the date window and return the normalised starts_at value.

    Empty or whitespace-only strings are treated as None (no start date).
    """
    # Normalise empty / whitespace-only strings to None
    if starts_at is not None:
        starts_at = starts_at.strip() or None

    expiry_date = parse_iso_date("expires_at", expires_at)
    if starts_at is not None:
        start_date = parse_iso_date("starts_at", starts_at)
        if start_date > expiry_date:
            raise HTTPException(
                status_code=400,
                detail="starts_at must be on or before expires_at."
            )
    return starts_at


def require_authenticated_teacher(request: Request) -> Dict[str, Any]:
    session_user = request.cookies.get("session_user")
    if not session_user:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": session_user})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def serialize_announcement(document: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "title": document["title"],
        "message": document["message"],
        "starts_at": document.get("starts_at"),
        "expires_at": document["expires_at"]
    }


def announcement_id_query(announcement_id: str) -> Dict[str, Any]:
    if ObjectId.is_valid(announcement_id):
        return {"_id": ObjectId(announcement_id)}
    return {"_id": announcement_id}


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get currently active announcements visible to all users."""
    today = date.today().isoformat()

    query = {
        "expires_at": {"$gte": today},
        "$or": [
            {"starts_at": {"$exists": False}},
            {"starts_at": None},
            {"starts_at": ""},
            {"starts_at": {"$lte": today}}
        ]
    }

    cursor = announcements_collection.find(query).sort("expires_at", 1)
    return [serialize_announcement(doc) for doc in cursor]


@router.get("/manage", response_model=List[Dict[str, Any]])
def list_all_announcements(request: Request) -> List[Dict[str, Any]]:
    """List all announcements for management (requires authentication)."""
    require_authenticated_teacher(request)

    cursor = announcements_collection.find({}).sort("expires_at", 1)
    return [serialize_announcement(doc) for doc in cursor]


@router.post("", response_model=Dict[str, Any])
def create_announcement(payload: AnnouncementCreate, request: Request) -> Dict[str, Any]:
    """Create an announcement (requires authentication)."""
    require_authenticated_teacher(request)
    normalized_starts_at = ensure_valid_date_window(payload.starts_at, payload.expires_at)

    insert_doc: Dict[str, Any] = {
        "title": payload.title.strip(),
        "message": payload.message.strip(),
        "expires_at": payload.expires_at
    }

    if normalized_starts_at:
        insert_doc["starts_at"] = normalized_starts_at

    result = announcements_collection.insert_one(insert_doc)
    created = announcements_collection.find_one({"_id": result.inserted_id})
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create announcement")

    return serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdate,
    request: Request
) -> Dict[str, Any]:
    """Update an existing announcement (requires authentication)."""
    require_authenticated_teacher(request)

    current = announcements_collection.find_one(announcement_id_query(announcement_id))
    if not current:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updates: Dict[str, Any] = {}
    if payload.title is not None:
        updates["title"] = payload.title.strip()
    if payload.message is not None:
        updates["message"] = payload.message.strip()
    if payload.expires_at is not None:
        updates["expires_at"] = payload.expires_at
    if payload.starts_at is not None:
        # Normalise whitespace-only strings to None (remove start date)
        updates["starts_at"] = payload.starts_at.strip() or None

    if not updates:
        raise HTTPException(status_code=400, detail="No changes provided")

    effective_starts_at = updates.get("starts_at", current.get("starts_at"))
    effective_expires_at = updates.get("expires_at", current["expires_at"])
    ensure_valid_date_window(effective_starts_at, effective_expires_at)

    result = announcements_collection.update_one(
        announcement_id_query(announcement_id),
        {"$set": updates}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one(announcement_id_query(announcement_id))
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to load updated announcement")

    return serialize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, request: Request) -> Dict[str, str]:
    """Delete an announcement (requires authentication)."""
    require_authenticated_teacher(request)

    result = announcements_collection.delete_one(announcement_id_query(announcement_id))
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
