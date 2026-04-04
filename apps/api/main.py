from fastapi import FastAPI

app = FastAPI(title="OpenChawn API")


@app.get("/")
def root():
    return {
        "status": "online",
        "message": "OpenChawn is alive"
    }
