from fastapi import FastAPI
from pydantic import BaseModel
import subprocess

app = FastAPI()


class RequestData(BaseModel):
    requestId: str


@app.post("/process/")
def process_request(data: RequestData):
    # Appelle ta fonction principale avec l'ID
    process = subprocess.run(
        ["python", "main.py", data.requestId, "?function=DoNothing"],
        capture_output=True, text=True
    )

    return {"output": process.stdout}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.2", port=8001)
