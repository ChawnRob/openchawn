from fastapi import FastAPI
from openai import OpenAI
import os

app = FastAPI(title="OpenChawn API")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.get("/")
def root():
    return {
        "status": "online",
        "message": "OpenChawn is alive"
    }

@app.get("/ask")
def ask(q: str):
    qei_score = qei_algo(q)

    prompt = f"""
    Tu es OpenChawn

    Niveau QEI: {qei_score}

    Si émotion basse -> empathique
    Si QEI élevé -> être direct et statégigique

    Question : {q}
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    return {
        "question": q,
        "qei_score": qei_score,
        "answer": response.output_text
    }
def qei_algo(input_data):
    qi_score = len(input_data) * 0.05

    qe_score = 0.5
    if "déçu" in input_data.lower():
        qe_score = 0.2
    elif "merci" in input_data.lower():
        qe_score = 0.8

    qei = (qi_score * 0.6 + qe_score * 0.4)

    return qei
