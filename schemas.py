# backend/schemas.py
"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    firebase_uid: Optional[str] = None

class LoginRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    firebase_uid: Optional[str] = None

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    email: Optional[str] = None


# ── Profile ───────────────────────────────────────────────────────
class ProfileCreate(BaseModel):
    name: str
    age: int = 0
    gender: str = "male"
    blood_group: str = "O+"
    profile_type: str = "myself"
    avatar_emoji: Optional[str] = None
    allergies: List[str] = []
    chronic_conditions: List[str] = []
    current_medications: List[str] = []

class ProfileResponse(BaseModel):
    id: str
    user_id: str
    name: str
    age: int
    gender: str
    blood_group: str
    profile_type: str
    avatar_emoji: Optional[str]
    allergies: List[str]
    chronic_conditions: List[str]
    current_medications: List[str]
    symptom_history: List[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Chat ──────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str       # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    language: str = "en"
    profile_context: Optional[dict] = None
    conversation_history: Optional[List[ChatMessage]] = []
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    is_emergency: bool = False
    suggestions: List[str] = []
    session_id: Optional[str] = None
    disclaimer: str = "⚠️ This is not a medical diagnosis. Please consult a qualified doctor."


# ── Health Log ────────────────────────────────────────────────────
class HealthLogCreate(BaseModel):
    profile_id: str
    date: Optional[datetime] = None
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    blood_sugar: Optional[float] = None
    heart_rate: Optional[float] = None
    weight: Optional[float] = None
    oxygen_saturation: Optional[float] = None
    water_intake: Optional[float] = None
    sleep_hours: Optional[float] = None
    notes: Optional[str] = None

class HealthLogResponse(BaseModel):
    id: str
    profile_id: str
    date: datetime
    systolic_bp: Optional[float]
    diastolic_bp: Optional[float]
    blood_sugar: Optional[float]
    heart_rate: Optional[float]
    weight: Optional[float]
    oxygen_saturation: Optional[float]
    water_intake: Optional[float]
    sleep_hours: Optional[float]
    notes: Optional[str]
    alerts: List[str] = []
    created_at: datetime

    class Config:
        from_attributes = True

class HealthLogSaveResponse(BaseModel):
    success: bool
    log_id: str
    alerts: List[str]
    message: str


# ── Report ────────────────────────────────────────────────────────
class ReportAnalysisResponse(BaseModel):
    report_id: str
    filename: str
    file_size_kb: float
    detected_type: str
    summary: str
    key_findings: List[str] = []
    recommendations: List[str] = []
    disclaimer: str = "⚠️ AI analysis is for informational purposes only. Consult a qualified physician."


# ── Dashboard ─────────────────────────────────────────────────────
class DashboardResponse(BaseModel):
    profile_id: str
    latest_log: Optional[HealthLogResponse]
    alerts: List[str]
    weekly_logs: List[HealthLogResponse]
    insights: List[str]
