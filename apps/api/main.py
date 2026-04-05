from fastapi import FastAPI
from datetime import datetime
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

 
    return {
        "question": q,
        "qei": qei,
        "answer": response
    }
   

