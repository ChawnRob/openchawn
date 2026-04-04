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
