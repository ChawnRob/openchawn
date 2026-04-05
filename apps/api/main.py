import json
import os
from typing import Any, Dict

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="OpenChawn API")


# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# CONFIG
# =========================
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small"


# =========================
# REQUEST MODEL
# =========================
class ChatRequest(BaseModel):
    message: str


# =========================
# HEALTH CHECK
# =========================
@app.get("/")
def root() -> Dict[str, str]:
    return {
        "status": "online",
        "message": "OpenChawn is alive"
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok"
    }


# =========================
# QEI ANALYSIS
# =========================
def analyze_qei(input_data: str) -> Dict[str, Any]:
    text = input_data.lower().strip()

    qi_score = 0.5
    qe_score = 0.5
    emotion_label = "neutral"
    emotion_intensity = 0.4
    urgency = 0.3
    recommended_tone = "clear"

    negative_words = [
        "déçu", "frustré", "colère", "énervé", "stresse", "stressé",
        "angoissé", "marche pas", "mauvais", "nul", "catastrophe",
        "bug", "problème", "erreur", "crash", "bloqué"
    ]

    positive_words = [
        "merci", "super", "content", "heureux", "top", "excellent",
        "parfait", "cool", "génial"
    ]

    urgency_words = [
        "urgent", "vite", "rapidement", "immédiat", "immédiatement",
        "maintenant", "asap", "tout de suite"
    ]

    strategic_words = [
        "stratégie", "vision", "structure", "architecture", "plan",
        "système", "optimisation", "business"
    ]

    word_count = len(text.split())

    if word_count >= 12:
        qi_score = 0.8
    elif word_count >= 6:
        qi_score = 0.65

    if any(word in text for word in urgency_words):
        urgency = 0.9
        recommended_tone = "direct"

    if any(word in text for word in negative_words):
        emotion_label = "negative"
        emotion_intensity = 0.8
        qe_score = 0.7
        if recommended_tone == "clear":
            recommended_tone = "empathetic"

    if any(word in text for word in positive_words):
        emotion_label = "positive"
        emotion_intensity = 0.7
        qe_score = 0.7
        if recommended_tone == "clear":
            recommended_tone = "reassuring"

    if any(word in text for word in strategic_words):
        qi_score = max(qi_score, 0.8)
        recommended_tone = "strategic"

    return {
        "qi_score": qi_score,
        "qe_score": qe_score,
        "emotion_label": emotion_label,
        "emotion_intensity": emotion_intensity,
        "urgency": urgency,
        "recommended_tone": recommended_tone
    }


# =========================
# MISTRAL CALL
# =========================
def call_mistral(prompt: str) -> str:
    if not MISTRAL_API_KEY:
        return "La clé API Mistral est absente. Ajoute MISTRAL_API_KEY dans Railway Variables."

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Tu es OpenChawn, une IA claire, stratégique et utile. "
                    "Réponds en français, avec précision, calme et structure."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    try:
        response = requests.post(
            MISTRAL_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except requests.exceptions.RequestException as e:
        return f"Erreur lors de l'appel API Mistral : {str(e)}"
    except (KeyError, IndexError, ValueError) as e:
        return f"Réponse Mistral invalide : {str(e)}"


# =========================
# RESPONSE GENERATION
# =========================
def generate_response(user_input: str, qei: Dict[str, Any]) -> Dict[str, str]:
    tone = qei["recommended_tone"]
    emotion = qei["emotion_label"]
    urgency = qei["urgency"]
    qi_score = qei["qi_score"]

    if tone == "empathetic":
        intro = "Je vois qu'il y a une tension réelle dans ce que tu dis."
    elif tone == "direct":
        intro = "On va aller droit au point."
    elif tone == "strategic":
        intro = "Ton message appelle une lecture stratégique."
    elif tone == "reassuring":
        intro = "On peut clarifier ça calmement."
    else:
        intro = "Analysons ça proprement."

    prompt = f"""
Question utilisateur : {user_input}

Contexte QEI :
- émotion : {emotion}
- urgence : {urgency}
- score logique : {qi_score}
- ton recommandé : {tone}

Consigne :
Réponds en français.
Sois utile, clair, structuré et concret.
Ne fais pas de phrases vagues.
"""

    ai_response = call_mistral(prompt)

    return {
        "intro": intro,
        "response": ai_response
    }


# =========================
# FILE LOGGING
# =========================
def save_record(record: Dict[str, Any]) -> None:
    try:
        with open("openchawn_data.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# =========================
# CHAT ENDPOINT
# =========================
@app.post("/chat")
def chat(input_data: ChatRequest) -> Dict[str, Any]:
    user_input = input_data.message.strip()

    if not user_input:
        raise HTTPException(status_code=400, detail="Le message est vide.")

    qei = analyze_qei(user_input)
    answer = generate_response(user_input, qei)

    record = {
        "input": user_input,
        "qei": qei,
        "answer": answer
    }
    save_record(record)

    return {
        "qei": qei,
        "answer": answer
    }

    return """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
    <meta charset="UTF-8">
    <title>OpenChawn</title>
    <style>
    body {
    font-family: Arial, sans-serif;
    background: radial-gradient(circle at top, #0f172a, #020617);
    color: #e2e8f0;
   }

h1 {
    font-size: 32px;
    background: linear-gradient(90deg, #38bdf8, #6366f1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
   }

input {
    width: 100%;
    padding: 18px;
    border-radius: 12px;
    border: none;
    outline: none;
    font-size: 16px;
    background: #0f172a;
    color: white;
    box-shadow: 0 0 0 1px #1e293b;
   }

button {
    margin-top: 10px;
    padding: 12px 20px;
    border-radius: 10px;
    border: none;
    background: linear-gradient(90deg, #38bdf8, #6366f1);
    color: white;
    cursor: pointer;
   }

.card {
    margin-top: 20px;
    padding: 20px;
    border-radius: 14px;
    background: #020617;
    box-shadow: 0 0 0 1px #1e293b;
   }
  
</style>
</head>

<body>

<div class="wrap">
    <h1>OpenChawn AI</h1>

    <input id="q" placeholder="Pose ta question...">
    <button onclick="sendAsk()">Analyser</button>

    <div id="result" style="display:none">

        <div class="card">
            <h3>Intro</h3>
            <p id="intro"></p>
        </div>

        <div class="card">
            <h3>Analyse</h3>
            <p><b>Emotion :</b> <span id="emotion"></span></p>
            <p><b>Urgence :</b> <span id="urgency"></span></p>
            <p><b>Ton :</b> <span id="tone"></span></p>
        </div>

        <div class="card">
            <h3>Actions</h3>
            <ul id="actions"></ul>
        </div>

        <div class="card">
            <h3>Conclusion</h3>
            <p id="closing"></p>
        </div>

    </div>
</div>

<script>
async function sendAsk() {

    const q = document.getElementById("q").value.trim();
    if (!q) return;

    const res = await fetch("/ask?q=" + encodeURIComponent(q));
    const data = await res.json();

    const r = data.answer;

    document.getElementById("result").style.display = "block";

    document.getElementById("intro").textContent = r.intro;
    document.getElementById("emotion").textContent = r.emotion;
    document.getElementById("urgency").textContent = r.urgency;
    document.getElementById("tone").textContent = r.tone;
    document.getElementById("closing").textContent = r.closing;

    const ul = document.getElementById("actions");
    ul.innerHTML = "";

    r.actions.forEach(a => {
        const li = document.createElement("li");
        li.textContent = a;
        ul.appendChild(li);
    });
}
</script>

</body>
</html>
"""    
 
