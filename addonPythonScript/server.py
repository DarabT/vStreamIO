from fastapi import FastAPI
from pydantic import BaseModel
import main  # Importer `main.py` une seule fois au démarrage du serveur

app = FastAPI()

class RequestData(BaseModel):
    requestId: str

@app.post("/process/")
def process_request(data: RequestData):
    # Appel direct à la fonction sans relancer le script
    result = main.main_rqst_from_server(data.requestId)
    if result:
        return {"output": str(result)}
    else:
        print("Erreur: ID de requête invalide")
        return {"output": "Erreur: ID de requête invalide"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.2", port=8001)
