from fastapi import FastAPI
from pydantic import BaseModel
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager

import asyncio
import os

import main  # Importer `main.py` une seule fois au démarrage du serveur

# variable global
# Fonction commune
common_cache = {}
cache_lock = asyncio.Lock()
CACHE_TIMEOUT = 30  # Si ce rqst ID n'est pas refresh depuis X secondes, clean de cette ID dans common_cache
CACHE_TEMPO = 5 # toute les X secondes reveille la fct pour checker les TIMEOUT des ID
# Pool partagé pour tout le serveur
max_workers_ProcessPoolExecutor = 0  # auto = nb de coeurs
if max_workers_ProcessPoolExecutor == 0:
    max_workers_ProcessPoolExecutor = os.cpu_count() or 4
process_pool = ProcessPoolExecutor(max_workers=max_workers_ProcessPoolExecutor)

# Sémaphore globale pour limiter le nombre de tâches CPU en même temps
semaphore = asyncio.Semaphore(max_workers_ProcessPoolExecutor)

async def cleanup_cache():
    while True:
        sleep_time = CACHE_TEMPO
        now = asyncio.get_event_loop().time()
        async with cache_lock:
            times_to_expire = []
            expired_ids = []

            for id, data in list(common_cache.items()):
                value = data["value"]
                last_access = data["last_access"]

                # --- Cas 1 : Future en cours -> on ignore tout pour cette entrée
                if isinstance(value, asyncio.Future) and not value.done():
                    continue

                # --- Cas 2 : Calcul expiration
                age = now - last_access
                remaining = CACHE_TIMEOUT - age

                if remaining > 0:
                    # encore valide → utilisé pour optimiser le prochain sleep
                    times_to_expire.append(remaining)
                else:
                    # expiré → à supprimer
                    expired_ids.append(id)

            # Déterminer temps du prochain réveil
            if times_to_expire:
                sleep_time = min(min(times_to_expire), CACHE_TEMPO)

            # Supprimer en une passe
            for id in expired_ids:
                print(f"Suppression du cache pour {id} (timeout)")
                del common_cache[id]

        await asyncio.sleep(sleep_time + 0.01)  # intervalle de nettoyage

async def get_common_info_async(id):
    global common_cache, cache_lock

    loop = asyncio.get_running_loop()

    # Accès au cache protégé par le lock
    async with cache_lock:
        if id in common_cache:
            data = common_cache[id]
            data["last_access"] = loop.time()
            value = data["value"]
            if isinstance(value, asyncio.Future):
                future = value
            else:
                return value
        else:
            # Pas en cache → créer future
            future = loop.create_future()
            common_cache[id] = {"value": future, "last_access": loop.time()}

    # Si future existe, attendre le résultat
    if isinstance(future, asyncio.Future):
        # Calcul lourd si la future n’a pas encore de résultat
        if not future.done():
            result = await loop.run_in_executor(None, main.main_commun, id)
            future.set_result(result)
            # Mettre à jour le cache avec le résultat réel
            async with cache_lock:
                common_cache[id] = {"value": result, "last_access": loop.time()}
        return await future

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

@app.on_event("startup")
async def startup_event():
    # Lancer la tâche de nettoyage en arrière-plan
    asyncio.create_task(cleanup_cache())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.2", port=8001)
