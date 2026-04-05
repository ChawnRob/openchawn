from fastapi import FastAPI
from datetime import datetime
from fastapi.responses import HTMLResponse
import json

app = FastAPI(title="OpenChawn API")

def save_interaction(question: str, qei: dict, answer: str):
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "question": question,
        "qei": qei,
        "answer": answer
    }

    with open("openchawn_data.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

@app.get("/")
def root():
    return {
        "status": "online",
        "message": "OpenChawn is alive"
    }


def analyze_qei(input_data: str) -> dict:
    text = input_data.lower().strip()

    qi_score = 0.5
    qe_score = 0.5
    emotion_label = "neutral"
    emotion_intensity = 0.4
    urgency = 0.3
    recommended_tone = "clear"

    word_count = len(text.split())

    # QI: plus le message est structuré/long, plus on monte légèrement
    if word_count >= 12:
        qi_score = 0.8
    elif word_count >= 6:
        qi_score = 0.65
    else:
        qi_score = 0.45

    # QE: détection émotionnelle simple
    negative_words = [
        "déçu", "frustré", "colère", "énervé", "perdu",
        "stressé", "angoissé", "marche pas", "bloqué", "problème",
        "mauvais", "nul", "catastrophe", "urgent", "help"
    ]
    positive_words = [
        "merci", "super", "content", "heureux", "génial",
        "top", "excellent", "parfait", "cool", "bravo"
    ]
    urgency_words = [
        "urgent", "vite", "rapidement", "immédiat",
        "maintenant", "asap", "tout de suite"
    ]
    strategic_words = [
        "stratégie", "scaler", "croissance", "business",
        "conversion", "clients", "offre", "positionnement", "marché"
    ]

    negative_hits = sum(1 for w in negative_words if w in text)
    positive_hits = sum(1 for w in positive_words if w in text)
    urgency_hits = sum(1 for w in urgency_words if w in text)
    strategic_hits = sum(1 for w in strategic_words if w in text)

    if negative_hits > 0:
        emotion_label = "frustration"
        qe_score = min(0.9, 0.45 + negative_hits * 0.12)
        emotion_intensity = min(0.95, 0.5 + negative_hits * 0.1)
        recommended_tone = "empathetic"

    if positive_hits > 0 and positive_hits >= negative_hits:
        emotion_label = "joy"
        qe_score = min(0.85, 0.45 + positive_hits * 0.1)
        emotion_intensity = min(0.9, 0.45 + positive_hits * 0.08)
        recommended_tone = "strategic"

    if urgency_hits > 0:
        urgency = min(1.0, 0.5 + urgency_hits * 0.15)
        recommended_tone = "direct"

    if strategic_hits > 0 and urgency_hits == 0 and negative_hits == 0:
        recommended_tone = "strategic"

    if emotion_label == "neutral" and urgency < 0.5 and strategic_hits == 0:
        recommended_tone = "clear"

    qei_score = round((qi_score * 0.6) + (qe_score * 0.4), 3)

    return {
        "qi_score": round(qi_score, 3),
        "qe_score": round(qe_score, 3),
        "qei_score": qei_score,
        "emotion_label": emotion_label,
        "emotion_intensity": round(emotion_intensity, 3),
        "urgency": round(urgency, 3),
        "recommended_tone": recommended_tone
    }


def generate_response(user_input: str, qei: dict) -> str:
    tone = qei["recommended_tone"]
    emotion = qei["emotion_label"]
    urgency = qei["urgency"]
    qi_score = qei["qi_score"]

    text = user_input.strip()

    if tone == "empathetic":
        intro = "Je vois qu’il y a une tension réelle dans ce que tu dis."
    elif tone == "direct":
        intro = "On va aller droit au point."
    elif tone == "strategic":
        intro = "Ton message appelle une lecture stratégique."
    elif tone == "reassuring":
        intro = "On peut clarifier ça calmement."
    else:
        intro = "Je vais te répondre clairement."

    actions = []

    if "restaurant" in text.lower() or "clients" in text.lower() or "business" in text.lower():
        actions.append("Regarde d’abord où tu perds la conversion : visibilité, réputation ou offre.")
        actions.append("Isole un problème principal au lieu de corriger 10 choses à la fois.")
        actions.append("Teste une action terrain immédiate sur 7 jours avant de tout reconstruire.")
    else:
        actions.append("Clarifie le vrai problème en une phrase.")
        actions.append("Sépare ce qui est émotionnel de ce qui est opérationnel.")
        actions.append("Choisis une seule prochaine action mesurable.")

    if urgency >= 0.7:
        actions.insert(0, "Traite d’abord l’urgence immédiate avant toute optimisation secondaire.")

    if qi_score >= 0.7:
        closing = "Si tu veux, la prochaine étape logique est de transformer ça en plan structuré."
    else:
        closing = "La clé maintenant, c’est de simplifier et agir tout de suite."

    response = (
        f"{intro}\n\n"
        f"Lecture rapide:\n"
        f"- émotion détectée: {emotion}\n"
        f"- niveau d’urgence: {urgency}\n"
        f"- ton conseillé: {tone}\n\n"
        f"Réponse:\n"
        f"1. {actions[0]}\n"
        f"2. {actions[1]}\n"
        f"3. {actions[2]}\n\n"
        f"{closing}"
    )

    return {
        "intro": intro,
        "summary": {
            "emotion": emotion,
            "urgency": urgency,
            "tone": tone
       },
        "actions": actions,
        "closing": closing     
    }
@app.get("/ask")
def ask(q: str):
    qei = analyze_qei(q)
    response = generate_response(q, qei)

    try:
        save_interaction(q, qei, response)
    except Exception as e:
        print("error saving:", e)
        
    return {
        "question": q,
        "qei": qei,
        "response": response
    }
   @app.get("/demo", response_class=HTMLResponse)
def demo():
    return """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>OpenChawn Demo</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #0b1020;
                color: #f5f7ff;
                margin: 0;
                padding: 40px;
            }
            .wrap {
                max-width: 900px;
                margin: 0 auto;
            }
            h1 {
                margin-bottom: 10px;
            }
            p {
                color: #b8c0ff;
            }
            textarea {
                width: 100%;
                min-height: 120px;
                border-radius: 12px;
                border: 1px solid #2a3566;
                background: #111833;
                color: white;
                padding: 16px;
                font-size: 16px;
                box-sizing: border-box;
            }
            button {
                margin-top: 14px;
                background: #5b7cff;
                color: white;
                border: 0;
                border-radius: 10px;
                padding: 12px 18px;
                font-size: 16px;
                cursor: pointer;
            }
            button:hover {
                opacity: 0.92;
            }
            .card {
                margin-top: 24px;
                background: #111833;
                border: 1px solid #24305c;
                border-radius: 16px;
                padding: 20px;
            }
            .label {
                color: #8ea0ff;
                font-size: 14px;
                margin-bottom: 6px;
            }
            .value {
                font-size: 18px;
                margin-bottom: 16px;
            }
            ul {
                padding-left: 20px;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 12px;
                margin-top: 18px;
            }
            .mini {
                background: #0d1430;
                border: 1px solid #24305c;
                border-radius: 12px;
                padding: 14px;
            }
            .muted {
                color: #b8c0ff;
                font-size: 14px;
            }
            @media (max-width: 700px) {
                .grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="wrap">
            <h1>OpenChawn Demo</h1>
            <p>Analyse QEI et réponse structurée en direct.</p>

            <textarea id="q" placeholder="Écris ton message ici..."></textarea>
            <br>
            <button onclick="sendAsk()">Analyser</button>

            <div id="result" class="card" style="display:none;">
                <div class="label">Intro</div>
                <div class="value" id="intro"></div>

                <div class="grid">
                    <div class="mini">
                        <div class="label">Émotion</div>
                        <div id="emotion"></div>
                    </div>
                    <div class="mini">
                        <div class="label">Urgence</div>
                        <div id="urgency"></div>
                    </div>
                    <div class="mini">
                        <div class="label">Ton</div>
                        <div id="tone"></div>
                    </div>
                </div>

                <div style="margin-top:20px;" class="label">Actions</div>
                <ul id="actions"></ul>

                <div style="margin-top:20px;" class="label">Closing</div>
                <div class="value" id="closing"></div>

                <div style="margin-top:24px;" class="label">QEI brut</div>
                <pre id="raw" class="muted" style="white-space:pre-wrap;"></pre>
            </div>
        </div>

        <script>
            async function sendAsk() {
                const q = document.getElementById("q").value.trim();
                if (!q) return;

                const res = await fetch(`/ask?q=${encodeURIComponent(q)}`);
                const data = await res.json();

                document.getElementById("result").style.display = "block";
                document.getElementById("intro").textContent = data.response.intro;
                document.getElementById("emotion").textContent = data.response.summary.emotion;
                document.getElementById("urgency").textContent = data.response.summary.urgency;
                document.getElementById("tone").textContent = data.response.summary.tone;
                document.getElementById("closing").textContent = data.response.closing;

                const actions = document.getElementById("actions");
                actions.innerHTML = "";
                data.response.actions.forEach(item => {
                    const li = document.createElement("li");
                    li.textContent = item;
                    actions.appendChild(li);
                });

                document.getElementById("raw").textContent = JSON.stringify(data.qei, null, 2);
            }
        </script>
    </body>
    </html>
    """
