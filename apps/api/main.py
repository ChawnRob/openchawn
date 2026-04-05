from fastapi import FastAPI
import requests
import json

app = FastAPI()

# =========================
# HEALTH CHECK
# =========================
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "OpenChawn is alive"
    }

# =========================
# QEI ANALYSIS
# =========================
def analyze_qei(input_data: str) -> dict:
    text = input_data.lower().strip()

    qi_score = 0.5
    qe_score = 0.5
    emotion_label = "neutral"
    emotion_intensity = 0.4
    urgency = 0.3
    recommended_tone = "clear"

    word_count = len(text.split())

    if word_count > 12:
        qi_score = 0.8
    elif word_count > 6:
        qi_score = 0.65

    if "urgent" in text or "vite" in text:
        urgency = 0.9

    if "merci" in text or "super" in text:
        emotion_label = "positive"
        emotion_intensity = 0.7

    if "problème" in text or "bug" in text:
        emotion_label = "negative"
        emotion_intensity = 0.8
        recommended_tone = "direct"

    return {
        "qi_score": qi_score,
        "qe_score": qe_score,
        "emotion_label": emotion_label,
        "emotion_intensity": emotion_intensity,
        "urgency": urgency,
        "recommended_tone": recommended_tone
    }

# =========================
# AI CALL (MISTRAL)
# =========================
def call_mistral(prompt: str) -> str:
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": "Bearer YOUR_API_KEY",
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistral-small",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    response = requests.post(url, headers=headers, json=data)
    return response.json()["choices"][0]["message"]["content"]

# =========================
# RESPONSE GENERATION
# =========================
def generate_response(user_input: str, qei: dict) -> dict:
    tone = qei["recommended_tone"]
    emotion = qei["emotion_label"]

    if tone == "empathetic":
        intro = "Je comprends qu'il y a une tension dans ce que tu dis."
    elif tone == "direct":
        intro = "On va aller droit au point."
    elif tone == "strategic":
        intro = "Ton message demande une approche stratégique."
    else:
        intro = "Analysons ça calmement."

    prompt = f"""
Utilisateur: {user_input}
Emotion: {emotion}
Réponds de manière {tone}.
"""

    ai_response = call_mistral(prompt)

    return {
        "intro": intro,
        "response": ai_response
    }

# =========================
# MAIN ENDPOINT
# =========================
@app.post("/chat")
def chat(input_data: dict):
    user_input = input_data.get("message", "")

    qei = analyze_qei(user_input)
    result = generate_response(user_input, qei)

    record = {
        "input": user_input,
        "qei": qei,
        "response": result
    }

    with open("openchawn_data.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "qei": qei,
        "answer": result
    }
@app.get("/demo", response_class=HTMLResponse)
def demo():

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
 
