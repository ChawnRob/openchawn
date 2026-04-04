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
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=q
    )

    return {
        "question": q,
        "answer": response.output_text
    }
def qei_algo(input_data, context="default"):
    qi_score = analyze_cognitive_signal(input_data)
    qe_profile = analyze_emotional_signal(input_data)

    weights = get_contextual_weights(context)
    qei_score = fuse_signals(
        qi=qi_score,
        qe=qe_profile["global_score"],
        qi_weight=weights["qi"],
        qe_weight=weights["qe"]
    )

    response_style = select_response_style(qei_score, qe_profile, context)
    response = generate_response(input_data, style=response_style)

    return {
        "response": response,
        "qei_score": qei_score,
        "qi_score": qi_score,
        "qe_profile": qe_profile,
        "style": response_style
    }
