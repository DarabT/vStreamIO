from fastapi import FastAPI
from pydantic import BaseModel
from concurrent.futures import ProcessPoolExecutor

import asyncio
import os

import main  # Importer `main.py` une seule fois au démarrage du serveur

# variable global
# Fonction commune
common_cache = {}
get_common_info_async_cmpt = 0
counter_lock = asyncio.Lock()
# Pool partagé pour tout le serveur
max_workers_ProcessPoolExecutor = 0  # auto = nb de coeurs
if max_workers_ProcessPoolExecutor == 0:
    max_workers_ProcessPoolExecutor = os.cpu_count() or 4
process_pool = ProcessPoolExecutor(max_workers=max_workers_ProcessPoolExecutor)

# Sémaphore globale pour limiter le nombre de tâches CPU en même temps
semaphore = asyncio.Semaphore(max_workers_ProcessPoolExecutor)


async def get_common_info_async(id):
    global common_cache, get_common_info_async_cmpt
    async with counter_lock:
        get_common_info_async_cmpt += 1

    try:
        if id in common_cache:
            # Si une tâche est en cours, attendons-la
            future = common_cache[id]
            if isinstance(future, asyncio.Future):
                return await future
            else:
                return future

        # Sinon, lançons le traduction id+recherche
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        common_cache[id] = future

        print(f"Recherche info en cours pour {id}…")
        result = main.main_commun(id)
        print(f"Résultat de recherche pour {id} : {str(result)}\n")

        future.set_result(result)
        common_cache[id] = result  # remplaçons la future par le résultat réel
        return result
    finally:
        async with counter_lock:
            get_common_info_async_cmpt -= 1
            if get_common_info_async_cmpt == 0:
                common_cache.clear()

async def run_traitement_limited(args):
    async with semaphore:  # attend si trop de jobs tournent déjà
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(process_pool, main.callTraitementWebSite, args)

app = FastAPI()

class RequestData(BaseModel):
    requestId: str
    addonKey: str

@app.post("/process/")
async def process_request(data: RequestData):
    # Appel direct à la fonction sans relancer le script
    args_list = await get_common_info_async(data.requestId)

    target_callTraitementWebSite = []

    for arg in args_list:
        if str("site="+data.addonKey) in arg[4]:
            target_callTraitementWebSite.append(arg)

    print("data.requestId : " +  str(data.requestId))
    print("data.addonKey : " +  str(data.addonKey))
    print(f"total result recherche pour {data.addonKey} : {len(target_callTraitementWebSite)}")
    print(f"result recherche pour {data.addonKey} : {target_callTraitementWebSite}")

    if not target_callTraitementWebSite:
        return {"output": []}  # rien trouvé pour cet addon
    else:
        # Lance les traitements spécifiques, mais sans saturer le CPU
        tasks = [run_traitement_limited(arg) for arg in target_callTraitementWebSite]
        results = await asyncio.gather(*tasks)

        # get les resultat et les organiser
        final_list = []

        for output_list in results:
            if output_list:
                final_list.extend(output_list)

        final_list.sort()
        final_list = main.enrich_streams_with_headers(final_list)  # post traitement des liens avec "User-Agent", "Referer" (Exemple les liens uqload)
        print(f"total repond pour {data.addonKey} : {len(final_list)}")
        print(str(data.addonKey) + " repond : " + str(final_list))
        return {"output": str(final_list)}

    """
    result = main.main_rqst_from_server(data.requestId)
    if result:
        a = {"output": str(result)}
        print(a)
        return {"output": str(result)}
    else:
        print("Erreur: ID de requête invalide")
        return {"output": "Erreur: ID de requête invalide"}
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.2", port=8001)
