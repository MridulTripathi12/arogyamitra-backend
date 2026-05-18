# backend/ai_service.py
"""
AI service layer — supports Gemini API and mock fallback.
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
    Try Gemini → Mock fallback.
    Returns the AI response text.
    """
    is_emergency = detect_emergency(message)
    if is_emergency:
        return EMERGENCY_RESPONSE_HI if language == "hi" else EMERGENCY_RESPONSE_EN

    system_prompt = build_system_prompt(profile)
    messages = []

    # Add conversation history (last 6 messages = 3 turns)
    for h in (history or [])[-6:]:
        role = "model" if h.role == "assistant" else "user"
        messages.append({"role": role, "parts": [{"text": h.content}]})
    messages.append({"role": "user", "parts": [{"text": message}]})

    # ── Try Gemini ───────────────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "systemInstruction": {"parts": [{"text": system_prompt}]},
                        "contents": messages,
                        "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7}
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "candidates" in data and data["candidates"]:
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        print(f"Gemini returned empty: {data}")
                else:
                    print(f"Gemini error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"Gemini exception: {e}")

    # ── Mock fallback ────────────────────────────────────────────
    return MOCK_RESPONSE_HI if language == "hi" else MOCK_RESPONSE_EN


def get_suggestions(message: str, language: str = "en") -> List[str]:
    """Generate contextual follow-up suggestions."""
    lower = message.lower()
    hi = language == "hi"
    if any(w in lower for w in ["fever", "temperature", "बुखार"]):
        return ["कौन सा तापमान खतरनाक है?" if hi else "What temperature is dangerous?", "बुखार के घरेलू उपाय" if hi else "Home remedies for fever", "डॉक्टर को कब दिखाएं?" if hi else "When to see a doctor?"]
    if any(w in lower for w in ["headache", "head pain", "सिरदर्द", "माइग्रेन"]):
        return ["माइग्रेन बनाम तनाव सिरदर्द" if hi else "Migraine vs tension headache", "सिरदर्द के उपाय" if hi else "Headache remedies", "न्यूरोलॉजिस्ट को कब दिखाएं?" if hi else "When to see a neurologist?"]
    if any(w in lower for w in ["sugar", "diabetes", "blood glucose", "शुगर", "मधुमेह"]):
        return ["सामान्य ब्लड शुगर रेंज" if hi else "Normal blood sugar ranges", "डायबिटिक डाइट टिप्स" if hi else "Diabetic diet tips", "HbA1c क्या है?" if hi else "HbA1c explained"]
    if any(w in lower for w in ["pressure", "bp", "hypertension", "रक्तचाप"]):
        return ["सामान्य बीपी रेंज" if hi else "Normal BP range", "रक्तचाप कम करने के प्राकृतिक तरीके" if hi else "Reduce blood pressure naturally", "बीपी की दवाओं की जानकारी" if hi else "BP medications overview"]
    if any(w in lower for w in ["sleep", "insomnia", "नींद"]):
        return ["नींद के टिप्स" if hi else "Sleep hygiene tips", "मुझे कितनी नींद की जरूरत है?" if hi else "How much sleep do I need?", "मेलाटोनिन - क्या यह सुरक्षित है?" if hi else "Melatonin — is it safe?"]
    if any(w in lower for w in ["weight", "obesity", "वजन"]):
        return ["स्वस्थ बीएमआई रेंज" if hi else "Healthy BMI range", "सुरक्षित वजन घटाने के टिप्स" if hi else "Safe weight loss tips", "वजन घटाने के लिए भारतीय आहार" if hi else "Indian diet for weight loss"]
    return [
        "मेरी दवाओं के बारे में बताएं" if hi else "Tell me about my medications",
        "सामान्य वाइटल रेंज क्या हैं?" if hi else "What are normal vital ranges?",
        "अपनी इम्युनिटी कैसे बढ़ाएं?" if hi else "How to improve my immunity?",
    ]


def compute_health_alerts(log, language: str = "en") -> List[str]:
    """Compute abnormal value alerts from a health log."""
    alerts = []
    hi = language == "hi"
    if log.systolic_bp and log.systolic_bp > 140:
        alerts.append(f"⚠️ {'उच्च सिस्टोलिक बीपी' if hi else 'High systolic BP'}: {log.systolic_bp:.0f} mmHg ({'सामान्य' if hi else 'normal'} < 120)")
    if log.diastolic_bp and log.diastolic_bp > 90:
        alerts.append(f"⚠️ {'उच्च डायस्टोलिक बीपी' if hi else 'High diastolic BP'}: {log.diastolic_bp:.0f} mmHg ({'सामान्य' if hi else 'normal'} < 80)")
    if log.systolic_bp and log.systolic_bp < 90:
        alerts.append(f"⚠️ {'निम्न रक्तचाप' if hi else 'Low blood pressure'}: {log.systolic_bp:.0f} mmHg")
    if log.blood_sugar and log.blood_sugar > 200:
        alerts.append(f"🚨 {'बहुत अधिक रक्त शर्करा' if hi else 'Very high blood sugar'}: {log.blood_sugar:.0f} mg/dL")
    if log.blood_sugar and log.blood_sugar < 70:
        alerts.append(f"🚨 {'निम्न रक्त शर्करा (हाइपोग्लाइसीमिया का खतरा)' if hi else 'Low blood sugar — risk of hypoglycemia'}: {log.blood_sugar:.0f} mg/dL")
    if log.heart_rate and log.heart_rate > 100:
        alerts.append(f"⚠️ {'उच्च हृदय गति' if hi else 'Elevated heart rate'}: {log.heart_rate:.0f} bpm (tachycardia)")
    if log.heart_rate and log.heart_rate < 50:
        alerts.append(f"⚠️ {'निम्न हृदय गति' if hi else 'Low heart rate'}: {log.heart_rate:.0f} bpm (bradycardia)")
    if log.oxygen_saturation and log.oxygen_saturation < 95:
        alerts.append(f"🚨 {'कम ऑक्सीजन' if hi else 'Low SpO₂'}: {log.oxygen_saturation:.0f}% — {'तुरंत डॉक्टर से मिलें' if hi else 'consult doctor immediately'}")
    if log.sleep_hours and log.sleep_hours < 5:
        alerts.append(f"⚠️ {'अपर्याप्त नींद' if hi else 'Insufficient sleep'}: {log.sleep_hours:.1f} hrs ({'अनुशंसित 7-9' if hi else 'recommended 7–9'})")
    if log.water_intake and log.water_intake < 1.5:
        alerts.append(f"💧 {'कम पानी' if hi else 'Low water intake'}: {log.water_intake:.1f} L ({'अनुशंसित 2-3 L' if hi else 'recommended 2–3 L'})")
    return alerts

async def analyze_image_with_ai(base64_img: str, mime_type: str, language: str = "en") -> str:
    """Analyze an image report using Gemini 1.5 Flash Vision."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    
    prompt = """Analyze this medical report image and provide a clear summary in plain language.
    You must act as a RAG-based diagnostic verification system. Verify the findings against the following knowledge bases and datasets:
    - Imaging Datasets: MIMIC-CXR, ChestX-ray8, HAM10000, SIIM-ISIC Melanoma Classification
    - Clinical & Textual Datasets: Medical Transcriptions (MTSamples), Disease-Symptom Knowledge Graph, MIMIC-IV
    - Knowledge Base & RAG Sources: PubMed Central (PMC), The Merck Manual, Cochrane Reviews, CORD-19

    Format your response exactly like this:
    1. Report type detected
    2. Key findings (list each value and whether it's normal/abnormal)
    3. What the patient should know
    4. Recommendations
    5. Diagnostic Verification & Citations (Cite relevant sources from the RAG datasets mentioned above to verify these findings)
    
    Always end with: '⚠️ This is not a medical diagnosis. Please consult a qualified doctor.'"""
    
    if language == "hi":
        prompt += "\n\nCRITICAL: Please provide the ENTIRE response in Hindi."

    if gemini_key:
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [
                            {
                                "parts": [
                                    {"text": prompt},
                                    {
                                        "inlineData": {
                                            "mimeType": mime_type,
                                            "data": base64_img
                                        }
                                    }
                                ]
                            }
                        ],
                        "generationConfig": {"maxOutputTokens": 1024}
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "candidates" in data and data["candidates"]:
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    return f"[Gemini returned empty: {data}]"
                return f"[Gemini Error: {resp.text[:200]}]"
        except Exception as e:
            return f"[Gemini Exception: {e}]"
            
    return "[API keys missing for vision analysis. Please configure GEMINI_API_KEY.]"
