# backend/main.py
"""
ArogyaMitra FastAPI Backend — Production-ready
- SQLite (dev) / PostgreSQL (prod)
- Claude + OpenAI AI integration
- JWT Authentication
- Health logs with abnormal value detection
- Medical report analysis
- Real-time chat with context
"""
import os
import io
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from dotenv import load_dotenv

load_dotenv()

from database import get_db, init_db
from models import UserModel, ProfileModel, HealthLogModel, ChatSessionModel, ReportModel
from schemas import (
    RegisterRequest, LoginRequest, AuthResponse,
    ProfileCreate, ProfileResponse,
    ChatRequest, ChatResponse,
    HealthLogCreate, HealthLogSaveResponse, HealthLogResponse,
    ReportAnalysisResponse, DashboardResponse,
)
from auth import hash_password, verify_password, create_access_token, get_user_id_from_token
from ai_service import get_ai_response, get_suggestions, detect_emergency, compute_health_alerts, analyze_image_with_ai
import base64

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(
    title="ArogyaMitra API",
    description="🏥 AI-powered multilingual health assistant — India's health companion",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


# ── Startup ───────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    await init_db()
    print("[OK] Database initialised")
    claude_ok = 'YES' if os.getenv('ANTHROPIC_API_KEY','').startswith('sk-ant') else 'not set'
    openai_ok = 'YES' if os.getenv('OPENAI_API_KEY','').startswith('sk-') else 'not set'
    print(f"[AI] Claude={claude_ok} | OpenAI={openai_ok}")
    print("[OK] ArogyaMitra API ready at http://localhost:8000/docs")


# ── Auth Helper ───────────────────────────────────────────────────
async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    if not credentials:
        return None
    return get_user_id_from_token(credentials.credentials)

async def require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


# ═══════════════════════════════════════════════════════════════════
# ROOT
# ═══════════════════════════════════════════════════════════════════
@app.get("/", tags=["Root"])
async def root():
    return {
        "app": "ArogyaMitra API v2.0",
        "status": "healthy",
        "message": "Serving health with ❤️",
        "docs": "/docs",
    }

@app.get("/health", tags=["Root"])
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ═══════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════
@app.post("/auth/register", response_model=AuthResponse, tags=["Auth"])
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register new user with email/password or Firebase UID."""
    # Check duplicate
    if body.email:
        result = await db.execute(select(UserModel).where(UserModel.email == body.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
    if body.phone:
        result = await db.execute(select(UserModel).where(UserModel.phone == body.phone))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone already registered")

    user = UserModel(
        id=str(uuid.uuid4()),
        name=body.name,
        email=body.email,
        phone=body.phone,
        firebase_uid=body.firebase_uid,
        password_hash=hash_password(body.password) if body.password else None,
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": user.id, "name": user.name})
    return AuthResponse(access_token=token, user_id=user.id, name=user.name, email=user.email)


@app.post("/auth/login", response_model=AuthResponse, tags=["Auth"])
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email/password or Firebase UID."""
    user = None

    if body.firebase_uid:
        result = await db.execute(
            select(UserModel).where(UserModel.firebase_uid == body.firebase_uid)
        )
        user = result.scalar_one_or_none()

    elif body.email and body.password:
        result = await db.execute(
            select(UserModel).where(UserModel.email == body.email)
        )
        user = result.scalar_one_or_none()
        if user and not verify_password(body.password, user.password_hash or ""):
            raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_access_token({"sub": user.id, "name": user.name})
    return AuthResponse(access_token=token, user_id=user.id, name=user.name, email=user.email)


@app.post("/auth/firebase", response_model=AuthResponse, tags=["Auth"])
async def firebase_login(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Login or register via Firebase UID (called after Firebase phone/Google auth)."""
    result = await db.execute(
        select(UserModel).where(UserModel.firebase_uid == body.firebase_uid)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = UserModel(
            id=str(uuid.uuid4()),
            name=body.name or "ArogyaMitra User",
            email=body.email,
            phone=body.phone,
            firebase_uid=body.firebase_uid,
        )
        db.add(user)
        await db.flush()

    token = create_access_token({"sub": user.id, "name": user.name})
    return AuthResponse(access_token=token, user_id=user.id, name=user.name, email=user.email)


# ═══════════════════════════════════════════════════════════════════
# PROFILES
# ═══════════════════════════════════════════════════════════════════
@app.get("/profiles", response_model=List[ProfileResponse], tags=["Profiles"])
async def list_profiles(
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfileModel).where(ProfileModel.user_id == user_id)
    )
    return result.scalars().all()


@app.post("/profiles", response_model=ProfileResponse, tags=["Profiles"])
async def create_profile(
    body: ProfileCreate,
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    profile = ProfileModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        **body.model_dump(),
    )
    db.add(profile)
    await db.flush()
    return profile


@app.put("/profiles/{profile_id}", response_model=ProfileResponse, tags=["Profiles"])
async def update_profile(
    profile_id: str,
    body: ProfileCreate,
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfileModel).where(
            ProfileModel.id == profile_id,
            ProfileModel.user_id == user_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    for k, v in body.model_dump().items():
        setattr(profile, k, v)
    return profile


@app.delete("/profiles/{profile_id}", tags=["Profiles"])
async def delete_profile(
    profile_id: str,
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfileModel).where(
            ProfileModel.id == profile_id,
            ProfileModel.user_id == user_id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.delete(profile)
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════════════════════════════
@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    body: ChatRequest,
    user_id: Optional[str] = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Main AI chat endpoint.
    - Supports Hindi & English
    - Emergency detection
    - Contextual suggestions
    - Saves session to DB if authenticated
    """
    is_emergency = detect_emergency(body.message)

    # Get or create session
    session = None
    if user_id and body.session_id:
        result = await db.execute(
            select(ChatSessionModel).where(ChatSessionModel.id == body.session_id)
        )
        session = result.scalar_one_or_none()

    # Build history from session if not provided
    history = body.conversation_history or []
    if session and not history:
        history = [
            type("Msg", (), {"role": m["role"], "content": m["content"]})()
            for m in (session.messages or [])
        ]

    # Get AI response
    reply = await get_ai_response(
        message=body.message,
        language=body.language,
        profile=body.profile_context,
        history=history,
    )

    suggestions = get_suggestions(body.message, body.language) if not is_emergency else [
        "Call 108 now", "Find nearest hospital", "Emergency first aid"
    ]

    # Save to session
    if user_id:
        session_messages = list(session.messages if session and session.messages else [])
        session_messages.append({"role": "user", "content": body.message, "timestamp": datetime.utcnow().isoformat()})
        session_messages.append({"role": "assistant", "content": reply, "timestamp": datetime.utcnow().isoformat()})

        if session:
            session.messages = session_messages
        else:
            profile_id = body.profile_context.get("id", "") if body.profile_context else ""
            new_session = ChatSessionModel(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                messages=session_messages,
                language=body.language,
            )
            db.add(new_session)
            await db.flush()
            session = new_session

    return ChatResponse(
        reply=reply,
        is_emergency=is_emergency,
        suggestions=suggestions,
        session_id=session.id if session else None,
    )


@app.get("/chat/history/{profile_id}", tags=["Chat"])
async def chat_history(
    profile_id: str,
    limit: int = 20,
    user_id: str = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSessionModel)
        .where(ChatSessionModel.profile_id == profile_id)
        .order_by(desc(ChatSessionModel.created_at))
        .limit(limit)
    )
    sessions = result.scalars().all()
    return [{"id": s.id, "messages": s.messages, "created_at": s.created_at} for s in sessions]


# ═══════════════════════════════════════════════════════════════════
# HEALTH LOGS
# ═══════════════════════════════════════════════════════════════════
@app.post("/health-logs", response_model=HealthLogSaveResponse, tags=["Health Logs"])
async def save_health_log(
    body: HealthLogCreate,
    user_id: Optional[str] = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    log = HealthLogModel(
        id=str(uuid.uuid4()),
        profile_id=body.profile_id,
        date=body.date or datetime.utcnow(),
        systolic_bp=body.systolic_bp,
        diastolic_bp=body.diastolic_bp,
        blood_sugar=body.blood_sugar,
        heart_rate=body.heart_rate,
        weight=body.weight,
        oxygen_saturation=body.oxygen_saturation,
        water_intake=body.water_intake,
        sleep_hours=body.sleep_hours,
        notes=body.notes,
    )
    db.add(log)
    await db.flush()

    alerts = compute_health_alerts(log)
    return HealthLogSaveResponse(
        success=True,
        log_id=log.id,
        alerts=alerts,
        message=f"Vitals logged successfully. {len(alerts)} alert(s) found.",
    )


@app.get("/health-logs/{profile_id}", tags=["Health Logs"])
async def get_health_logs(
    profile_id: str,
    days: int = 7,
    user_id: Optional[str] = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(HealthLogModel)
        .where(HealthLogModel.profile_id == profile_id)
        .order_by(desc(HealthLogModel.date))
        .limit(days)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "profile_id": l.profile_id,
            "date": l.date.isoformat() if l.date else None,
            "systolic_bp": l.systolic_bp,
            "diastolic_bp": l.diastolic_bp,
            "blood_sugar": l.blood_sugar,
            "heart_rate": l.heart_rate,
            "weight": l.weight,
            "oxygen_saturation": l.oxygen_saturation,
            "water_intake": l.water_intake,
            "sleep_hours": l.sleep_hours,
            "notes": l.notes,
            "alerts": compute_health_alerts(l),
        }
        for l in logs
    ]


@app.get("/dashboard/{profile_id}", tags=["Health Logs"])
async def get_dashboard(
    profile_id: str,
    user_id: Optional[str] = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Returns latest vitals, alerts, weekly trends, and AI insights."""
    result = await db.execute(
        select(HealthLogModel)
        .where(HealthLogModel.profile_id == profile_id)
        .order_by(desc(HealthLogModel.date))
        .limit(7)
    )
    logs = result.scalars().all()

    latest = logs[0] if logs else None
    alerts = compute_health_alerts(latest) if latest else []

    # AI insights (static for now, can be made dynamic)
    insights = []
    if latest:
        if latest.systolic_bp and latest.systolic_bp > 130:
            insights.append("💡 Consider reducing sodium intake and increasing potassium-rich foods")
        if latest.sleep_hours and latest.sleep_hours < 6:
            insights.append("💡 Consistent sleep deprivation increases cardiovascular risk")
        if latest.water_intake and latest.water_intake < 2:
            insights.append("💡 Increase water intake — dehydration affects concentration and kidney health")

    return {
        "profile_id": profile_id,
        "latest_log": {
            "systolic_bp": latest.systolic_bp,
            "diastolic_bp": latest.diastolic_bp,
            "blood_sugar": latest.blood_sugar,
            "heart_rate": latest.heart_rate,
            "weight": latest.weight,
            "oxygen_saturation": latest.oxygen_saturation,
            "water_intake": latest.water_intake,
            "sleep_hours": latest.sleep_hours,
            "date": latest.date.isoformat() if latest and latest.date else None,
        } if latest else None,
        "alerts": alerts,
        "insights": insights,
        "weekly_logs": [
            {
                "date": l.date.isoformat() if l.date else None,
                "heart_rate": l.heart_rate,
                "systolic_bp": l.systolic_bp,
                "blood_sugar": l.blood_sugar,
                "sleep_hours": l.sleep_hours,
                "oxygen_saturation": l.oxygen_saturation,
            }
            for l in reversed(logs)
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════════════════════════════
@app.post("/analyze-report", response_model=ReportAnalysisResponse, tags=["Reports"])
async def analyze_report(
    profile_id: str = "demo",
    file: UploadFile = File(...),
    user_id: Optional[str] = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Upload and analyse a medical report (PDF or image)."""
    allowed = ["application/pdf", "image/jpeg", "image/png", "image/jpg"]
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Upload PDF, JPG, or PNG only")

    content = await file.read()
    file_size_kb = len(content) / 1024
    is_pdf = "pdf" in (file.content_type or "")

    # AI Analysis
    ai_summary = ""
    extracted_text = ""

    if is_pdf:
        # PDF Text Extraction
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            extracted_text = " ".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            extracted_text = ""

        if extracted_text and len(extracted_text) > 50:
            prompt = f"""Analyze this medical report text and provide a clear summary in plain language:
{extracted_text[:4000]}

Format your response as:
1. Report type detected
2. Key findings (list each value and whether it's normal/abnormal)
3. What the patient should know
4. Recommendations

Always end with: '⚠️ This is not a medical diagnosis. Please consult a qualified doctor.'"""
            ai_summary = await get_ai_response(prompt, language="en", profile=None, history=[])
        else:
            ai_summary = "[Could not extract readable text from this PDF. It may be a scanned image.]"
    else:
        # Image Vision Analysis
        b64_img = base64.b64encode(content).decode('utf-8')
        ai_summary = await analyze_image_with_ai(b64_img, file.content_type)

    # Save report record
    report = ReportModel(
        id=str(uuid.uuid4()),
        profile_id=profile_id,
        filename=file.filename or "report",
        file_type="pdf" if is_pdf else "image",
        extracted_text=extracted_text[:5000] if extracted_text else None,
        ai_summary=ai_summary,
        file_size_kb=round(file_size_kb, 1),
    )
    db.add(report)

    return ReportAnalysisResponse(
        report_id=report.id,
        filename=file.filename or "report",
        file_size_kb=round(file_size_kb, 1),
        detected_type="PDF Report" if is_pdf else "Medical Image",
        summary=ai_summary,
        key_findings=[],
        recommendations=["Discuss findings with your doctor"],
    )


@app.get("/reports/{profile_id}", tags=["Reports"])
async def list_reports(
    profile_id: str,
    user_id: Optional[str] = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ReportModel)
        .where(ReportModel.profile_id == profile_id)
        .order_by(desc(ReportModel.created_at))
        .limit(20)
    )
    reports = result.scalars().all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "file_type": r.file_type,
            "file_size_kb": r.file_size_kb,
            "summary": r.ai_summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]
