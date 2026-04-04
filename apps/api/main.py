from fastapi import FastAPI
from openai import OpenAI
import os
import json

app = FastAPI(title="OpenChawn API")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.get("/")
def root():
    return {
        "status": "online",
        "message": "OpenChawn is alive"
    }


def analyze_qei(input_data: str):
    analysis_prompt = f"""
Analyse ce message utilisateur et retourne uniquement un JSON valide.

Message :
{input_data}

Retourne exactement ce format :
{{
  "qi_score": 0.0,
  "qe_score": 0.0,
  "emotion_label": "neutral",
  "emotion_intensity": 0.0,
  "urgency": 0.0,
  "recommended_tone": "clear"
}}

Règles :
- qi_score = niveau de structure / clarté / logique perçue, entre 0 et 1
- qe_score = charge émotionnelle globale, entre 0 et 1
- emotion_label = une valeur parmi: joy, frustration, anger, sadness, fear, neutral, excitement
- emotion_intensity = intensité émotionnelle entre 0 et 1
- urgency = urgence perçue entre 0 et 1
- recommended_tone = un parmi: empathetic, calm, strategic, direct, reassuring

Ne retourne rien d'autre que le JSON.
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=analysis_prompt
    )

    raw_text = ""
    if hasattr(response, "output_text") and response.output_text:
        raw_text = response.output_text.strip()
    else:
        try:
            raw_text = response.output[0].content[0].text.strip()
        except Exception:
            raw_text = ""

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = {
            "qi_score": 0.5,
            "qe_score": 0.5,
            "emotion_label": "neutral",
            "emotion_intensity": 0.5,
            "urgency": 0.5,
            "recommended_tone": "clear"
        }

    qi_score = float(data.get("qi_score", 0.5))
    qe_score = float(data.get("qe_score", 0.5))

    qei_score = round((qi_score * 0.6) + (qe_score * 0.4), 3)

    return {
        "qi_score": qi_score,
        "qe_score": qe_score,
        "qei_score": qei_score,
        "emotion_label": data.get("emotion_label", "neutral"),
        "emotion_intensity": float(data.get("emotion_intensity", 0.5)),
        "urgency": float(data.get("urgency", 0.5)),
        "recommended_tone": data.get("recommended_tone", "clear")
    }


@app.get("/ask")
def ask(q: str):
    qei = analyze_qei(q)

    response_prompt = f"""
Tu es OpenChawn, une IA business premium, lucide, utile et stratégique.

Profil QEI détecté :
- qi_score: {qei["qi_score"]}
- qe_score: {qei["qe_score"]}
- qei_score: {qei["qei_score"]}
- emotion_label: {qei["emotion_label"]}
- emotion_intensity: {qei["emotion_intensity"]}
- urgency: {qei["urgency"]}
- recommended_tone: {qei["recommended_tone"]}

Règles :
- adapte ton ton selon recommended_tone
- si émotion négative, commence par reconnaître brièvement l'état émotionnel
- si urgence élevée, sois plus direct et priorise l'action
- si qi_score élevé, réponds de manière plus stratégique et structurée
- reste clair, humain, utile
- ne flatte pas inutilement
- donne une réponse exploitable

Message utilisateur :
{q}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=response_prompt
    )

    answer = ""
    if hasattr(response, "output_text") and response.output_text:
        answer = response.output_text
    else:
        try:
            answer = response.output[0].content[0].text
        except Exception:
            answer = str(response)

    return {
        "question": q,
        "qei": qei,
        "answer": answer
    }
