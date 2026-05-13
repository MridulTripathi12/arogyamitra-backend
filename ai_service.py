# backend/ai_service.py
"""
AI service layer — supports Claude (Anthropic), OpenAI, and mock fallback.
Auto-detects available API key and uses the best available model.
"""
import os
import httpx
from typing import Optional, List
from schemas import ChatMessage

# ── Emergency Detection ───────────────────────────────────────────
EMERGENCY_EN = [
    "chest pain", "heart attack", "stroke", "can't breathe", "cannot breathe",
    "not breathing", "shortness of breath", "suicidal", "kill myself",
    "want to die", "end my life", "unconscious", "unresponsive",
    "severe bleeding", "choking", "seizure", "collapsed", "overdose",
    "poisoning", "anaphylaxis", "allergic reaction severe",
]
EMERGENCY_HI = [
    "सीने में दर्द", "दिल का दौरा", "स्ट्रोक", "सांस नहीं", "सांस रुक",
    "आत्महत्या", "मरना चाहता", "मरना चाहती", "बेहोश", "खून बह रहा",
    "दौरा पड़", "जहर खा", "सांस नहीं आ रही",
]

def detect_emergency(text: str) -> bool:
    lower = text.lower()
    for kw in EMERGENCY_EN:
        if kw in lower:
            return True
    for kw in EMERGENCY_HI:
        if kw in text:
            return True
    return False


# ── System Prompt ─────────────────────────────────────────────────
def build_system_prompt(profile: Optional[dict] = None) -> str:
    profile_ctx = ""
    if profile:
        profile_ctx = f"""
Patient Profile:
- Name: {profile.get('name', 'Unknown')}
- Age: {profile.get('age', 'Unknown')}
- Blood Group: {profile.get('blood_group', 'Unknown')}
- Profile Type: {profile.get('profile_type', 'myself')}
- Known Conditions: {', '.join(profile.get('chronic_conditions', [])) or 'None'}
- Current Medications: {', '.join(profile.get('current_medications', [])) or 'None'}
- Known Allergies: {', '.join(profile.get('allergies', [])) or 'None'}

Use this profile context to personalise your health guidance.
"""

    return f"""You are ArogyaMitra, an AI health assistant for Indian users. You are compassionate, knowledgeable, and safe.

{profile_ctx}

STRICT RULES:
1. NEVER diagnose with medical certainty. Use phrases like "this may suggest", "could indicate", "often associated with"
2. ALWAYS end every response with: "⚠️ This is not a medical diagnosis. Please consult a qualified doctor."
3. If user mentions chest pain, stroke, suicidal thoughts, inability to breathe, unconsciousness, or severe bleeding — respond with emergency guidance ONLY
4. Support Hindi and English — respond in the same language the user writes in
5. Be culturally sensitive to Indian health contexts, Ayurvedic practices, and Indian dietary habits
6. Keep responses clear and accessible to non-medical users — avoid heavy jargon
7. Never recommend specific prescription dosages — only general wellness guidance
8. For children or elderly profiles, be extra cautious and always recommend professional consultation

You can discuss: symptoms, general wellness, nutrition, lifestyle, understanding medical terms, medication side effects (general), mental health support, and preventive healthcare."""


# ── AI Response ───────────────────────────────────────────────────
EMERGENCY_RESPONSE_EN = """🚨 **EMERGENCY DETECTED**

The symptoms you've described may require **immediate medical attention**.

**Please act NOW:**
• Call **108** (Ambulance) or **112** (Emergency)
• Go to the nearest hospital emergency department
• Do not eat or drink anything
• Stay calm and have someone stay with you

**If unconscious:**
• Place in recovery position
• Begin CPR if not breathing
• Keep airway clear

⚠️ **This is a medical emergency. Do not wait — seek help immediately.**"""

EMERGENCY_RESPONSE_HI = """🚨 **आपातकाल पहचाना गया**

आपने जो लक्षण बताए हैं उनके लिए **तुरंत चिकित्सा सहायता** आवश्यक हो सकती है।

**अभी कार्रवाई करें:**
• **108** (एम्बुलेंस) या **112** (इमरजेंसी) पर कॉल करें
• नजदीकी अस्पताल के आपातकालीन विभाग में जाएं
• कुछ खाएं-पिएं नहीं
• शांत रहें, किसी को पास रखें

⚠️ **यह चिकित्सा आपातकाल है। प्रतीक्षा न करें — तुरंत सहायता लें।**"""

MOCK_RESPONSE_EN = """I understand your concern. Here is some general health information based on what you've shared.

**General wellness reminders:**
• Stay well-hydrated — aim for 8–10 glasses of water daily
• Maintain regular sleep schedule (7–9 hours)
• Eat a balanced diet rich in fruits and vegetables
• Exercise moderately for at least 30 minutes daily
• Monitor any worsening or new symptoms

If your symptoms persist or worsen, please consult a healthcare provider promptly.

⚠️ This is not a medical diagnosis. Please consult a qualified doctor."""

MOCK_RESPONSE_HI = """मैं आपकी चिंता समझता हूं। आपने जो बताया है उसके आधार पर कुछ सामान्य स्वास्थ्य जानकारी:

**सामान्य स्वास्थ्य सुझाव:**
• पर्याप्त पानी पियें — प्रतिदिन 8–10 गिलास
• नियमित नींद लें (7–9 घंटे)
• संतुलित आहार लें
• रोज़ाना 30 मिनट व्यायाम करें
• लक्षणों की निगरानी करें

यदि लक्षण जारी रहें या बिगड़ें तो तुरंत डॉक्टर से मिलें।

⚠️ यह चिकित्सा निदान नहीं है। कृपया किसी योग्य डॉक्टर से परामर्श लें।"""


async def get_ai_response(
    message: str,
    language: str = "en",
    profile: Optional[dict] = None,
    history: Optional[List[ChatMessage]] = None,
) -> str:
    """
    Try Claude → OpenAI → Mock fallback.
    Returns the AI response text.
    """
    is_emergency = detect_emergency(message)
    if is_emergency:
        return EMERGENCY_RESPONSE_HI if language == "hi" else EMERGENCY_RESPONSE_EN

    system_prompt = build_system_prompt(profile)
    messages = []

    # Add conversation history (last 6 messages = 3 turns)
    for h in (history or [])[-6:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": message})

    # ── Try Claude ───────────────────────────────────────────────
    claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    if claude_key and claude_key.startswith("sk-ant"):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": claude_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 1024,
                        "system": system_prompt,
                        "messages": messages,
                    },
                )
                if resp.status_code == 200:
                    return resp.json()["content"][0]["text"]
                print(f"Claude error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"Claude exception: {e}")

    # ── Try OpenAI ───────────────────────────────────────────────
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key and openai_key.startswith("sk-"):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "system", "content": system_prompt}] + messages,
                        "max_tokens": 1024,
                        "temperature": 0.7,
                    },
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                print(f"OpenAI error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"OpenAI exception: {e}")

    # ── Mock fallback ────────────────────────────────────────────
    return MOCK_RESPONSE_HI if language == "hi" else MOCK_RESPONSE_EN


def get_suggestions(message: str, language: str = "en") -> List[str]:
    """Generate contextual follow-up suggestions."""
    lower = message.lower()
    if any(w in lower for w in ["fever", "temperature", "बुखार"]):
        return ["What temperature is dangerous?", "Home remedies for fever", "When to see a doctor?"]
    if any(w in lower for w in ["headache", "head pain", "सिरदर्द", "माइग्रेन"]):
        return ["Migraine vs tension headache", "Headache remedies", "When to see a neurologist?"]
    if any(w in lower for w in ["sugar", "diabetes", "blood glucose", "शुगर", "मधुमेह"]):
        return ["Normal blood sugar ranges", "Diabetic diet tips", "HbA1c explained"]
    if any(w in lower for w in ["pressure", "bp", "hypertension", "रक्तचाप"]):
        return ["Normal BP range", "Reduce blood pressure naturally", "BP medications overview"]
    if any(w in lower for w in ["sleep", "insomnia", "नींद"]):
        return ["Sleep hygiene tips", "How much sleep do I need?", "Melatonin — is it safe?"]
    if any(w in lower for w in ["weight", "obesity", "वजन"]):
        return ["Healthy BMI range", "Safe weight loss tips", "Indian diet for weight loss"]
    return [
        "Tell me about my medications",
        "What are normal vital ranges?",
        "How to improve my immunity?",
    ]


def compute_health_alerts(log) -> List[str]:
    """Compute abnormal value alerts from a health log."""
    alerts = []
    if log.systolic_bp and log.systolic_bp > 140:
        alerts.append(f"⚠️ High systolic BP: {log.systolic_bp:.0f} mmHg (normal < 120)")
    if log.diastolic_bp and log.diastolic_bp > 90:
        alerts.append(f"⚠️ High diastolic BP: {log.diastolic_bp:.0f} mmHg (normal < 80)")
    if log.systolic_bp and log.systolic_bp < 90:
        alerts.append(f"⚠️ Low blood pressure: {log.systolic_bp:.0f} mmHg")
    if log.blood_sugar and log.blood_sugar > 200:
        alerts.append(f"🚨 Very high blood sugar: {log.blood_sugar:.0f} mg/dL")
    if log.blood_sugar and log.blood_sugar < 70:
        alerts.append(f"🚨 Low blood sugar: {log.blood_sugar:.0f} mg/dL — risk of hypoglycemia")
    if log.heart_rate and log.heart_rate > 100:
        alerts.append(f"⚠️ Elevated heart rate: {log.heart_rate:.0f} bpm (tachycardia)")
    if log.heart_rate and log.heart_rate < 50:
        alerts.append(f"⚠️ Low heart rate: {log.heart_rate:.0f} bpm (bradycardia)")
    if log.oxygen_saturation and log.oxygen_saturation < 95:
        alerts.append(f"🚨 Low SpO₂: {log.oxygen_saturation:.0f}% — consult doctor immediately")
    if log.sleep_hours and log.sleep_hours < 5:
        alerts.append(f"⚠️ Insufficient sleep: {log.sleep_hours:.1f} hrs (recommended 7–9)")
    if log.water_intake and log.water_intake < 1.5:
        alerts.append(f"💧 Low water intake: {log.water_intake:.1f} L (recommended 2–3 L)")
    return alerts
