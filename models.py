# backend/models.py
"""
SQLAlchemy ORM models for all database tables.
"""
from sqlalchemy import (
    Column, String, Float, Integer, Date, DateTime, Boolean, Text, JSON
)
from sqlalchemy.dialects.sqlite import TEXT
from database import Base
from datetime import datetime
import uuid


def gen_id():
    return str(uuid.uuid4())


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    firebase_uid = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)
    fcm_token = Column(String, nullable=True)   # For push notifications
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class ProfileModel(Base):
    __tablename__ = "health_profiles"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer, default=0)
    gender = Column(String, default="male")
    blood_group = Column(String, default="O+")
    profile_type = Column(String, default="myself")
    avatar_emoji = Column(String, nullable=True)
    allergies = Column(JSON, default=list)
    chronic_conditions = Column(JSON, default=list)
    current_medications = Column(JSON, default=list)
    symptom_history = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HealthLogModel(Base):
    __tablename__ = "health_logs"

    id = Column(String, primary_key=True, default=gen_id)
    profile_id = Column(String, nullable=False, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    systolic_bp = Column(Float, nullable=True)
    diastolic_bp = Column(Float, nullable=True)
    blood_sugar = Column(Float, nullable=True)
    heart_rate = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    oxygen_saturation = Column(Float, nullable=True)
    water_intake = Column(Float, nullable=True)
    sleep_hours = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatSessionModel(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=gen_id)
    profile_id = Column(String, nullable=False, index=True)
    messages = Column(JSON, default=list)      # List of {role, content, timestamp}
    language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReportModel(Base):
    __tablename__ = "medical_reports"

    id = Column(String, primary_key=True, default=gen_id)
    profile_id = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)          # "pdf" | "image"
    extracted_text = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    file_size_kb = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
