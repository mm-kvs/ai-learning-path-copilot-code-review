"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)

MAX_MESSAGE_LENGTH = 500


class AnnouncementInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    start_date: Optional[date] = None
    expiration_date: date


def require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    """Ensure the request comes from a signed-in teacher"""
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")
    return teacher


def parse_object_id(announcement_id: str) -> ObjectId:
    try:
        return ObjectId(announcement_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="Announcement not found")


def validate_announcement(announcement: AnnouncementInput) -> Dict[str, Any]:
    """Validate input and convert it to a database document"""
    message = announcement.message.strip()
    if not message:
        raise HTTPException(
            status_code=422, detail="Announcement message cannot be empty")

    if announcement.start_date and announcement.start_date > announcement.expiration_date:
        raise HTTPException(
            status_code=422, detail="Start date must be on or before the expiration date")

    return {
        "message": message,
        "start_date": announcement.start_date.isoformat() if announcement.start_date else None,
        "expiration_date": announcement.expiration_date.isoformat()
    }


def serialize(announcement: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(announcement["_id"]),
        "message": announcement["message"],
        "start_date": announcement.get("start_date"),
        "expiration_date": announcement["expiration_date"],
        "created_by": announcement.get("created_by")
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements that are currently active (public)"""
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": today}}
        ]
    }
    cursor = announcements_collection.find(query).sort("expiration_date", 1)
    return [serialize(a) for a in cursor]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements, including scheduled and expired - requires authentication"""
    require_teacher(teacher_username)
    cursor = announcements_collection.find().sort("expiration_date", -1)
    return [serialize(a) for a in cursor]


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_announcement(
    announcement: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement - requires authentication"""
    teacher = require_teacher(teacher_username)
    document = validate_announcement(announcement)
    document["created_by"] = teacher["_id"]

    result = announcements_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize(document)


@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement - requires authentication"""
    require_teacher(teacher_username)
    object_id = parse_object_id(announcement_id)
    document = validate_announcement(announcement)

    result = announcements_collection.update_one(
        {"_id": object_id}, {"$set": document})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return serialize(announcements_collection.find_one({"_id": object_id}))


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement - requires authentication"""
    require_teacher(teacher_username)
    object_id = parse_object_id(announcement_id)

    result = announcements_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
