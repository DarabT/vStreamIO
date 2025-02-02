# -*- coding: utf-8 -*-
# Ajout des chemins vers sources
import sys  # to communicate with node.js
import os.path
from concurrent.futures import ProcessPoolExecutor

__DEBUG__ = False

path = os.path.realpath(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(path))
if (parent_dir + '\\vStreamKodi\\plugin.video.vstream') not in sys.path:
    sys.path.insert(0, parent_dir + '\\vStreamKodi\\plugin.video.vstream')
if (parent_dir + '\\KodiStub') not in sys.path:
    sys.path.insert(0, parent_dir + '\\KodiStub')

from resources.lib.search import cSearch
from imdb import IMDb
import xbmcplugin
import subprocess
from concurrent.futures import ThreadPoolExecutor
import ast
import time

################################## IMDb incapable de me dire si c'est un anime ou pas utilisation de BeautifulSoup pour catch les Tags et vérfier si "anime" est dedans ##########################################
import requests
from bs4 import BeautifulSoup


def get_imdb_interests_anime_or_not(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
    }

    # Envoi de la requête pour obtenir la page
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Erreur de récupération de la page : {response.status_code}")
        return []

    # Parse le contenu HTML de la page
    soup = BeautifulSoup(response.text, 'html.parser')

    # Affichage d'une partie du HTML pour vérification (optionnel)
    # print(soup.prettify())

    # Recherche des balises <a> avec la classe 'ipc-chip__text' qui contiennent les intérêts
    interests = [span.text.strip().lower() for span in soup.find_all('span', {'class': 'ipc-chip__text'})]

    if interests:
        if 'anime' in interests:
            return True
        else:
            return False
    else:
        if __DEBUG__:
            print("Aucun intérêt trouvé.")
        return False
############################################################################


def obtenirTitreFilm(imdb_id):

    # Fonction pour mesurer le temps d'exécution de `get_imdb_interests_anime_or_not`
    def fetch_bAnime():
        if __DEBUG__:
            start_time = time.time()
        url = "https://www.imdb.com/title/" + imdb_id + "/"
        result = get_imdb_interests_anime_or_not(url)
        if __DEBUG__:
            elapsed = time.time() - start_time
            print(f"Temps d'exécution de get_imdb_interests_anime_or_not: {elapsed:.4f} secondes")
        return result

    # Fonction pour mesurer le temps d'exécution de `ia.get_movie`
    def fetch_film():
        if __DEBUG__:
            start_time = time.time()
        ia = IMDb()
        result = ia.get_movie(imdb_id[2:], info=['main', 'plot'])
        if __DEBUG__:
            elapsed = time.time() - start_time
            print(f"Temps d'exécution de ia.get_movie: {elapsed:.4f} secondes")
        return result

    # TODO la mesure du temps montre que "BeautifulSoup" est plus rapide pour savoir si c'est un anime ou pas, peut-être l'appliquer uniquement lui pour avoir les infos 'title' et 'type'
    # Exécuter les deux appels en parallèle avec ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_bAnime = executor.submit(fetch_bAnime)
        future_film = executor.submit(fetch_film)

        # Récupération des résultats des deux appels
        bAnime = future_bAnime.result()
        film = future_film.result()

    if film: #match trouver
        title = film.get('title', '')
        type = film.get('kind', '').lower()
        #genres = [genre.lower() for genre in film.get('genres', [])] n'extrait pas tout les tag et sur certain resultat "anime" n'apparait pas dans la liste

        if bAnime:
            sCat = 3  # "3" pour "URL_SEARCH_ANIMS" (type ne fait pas la distingtion entre un Anim série/film et une série/film solution de secours pour l'instant TODO trouver mieux ?)
        elif type == 'movie':
            sCat = 1 # "1" pour "URL_SEARCH_MOVIES"
        elif type in ['tv series', 'tv mini series']:
            sCat = 2 # "2" pour "URL_SEARCH_SERIES"
        elif type == 'anime':
            sCat = 3 # "3" pour "URL_SEARCH_ANIMS"
        elif type == 'documentary':
            sCat = 5 # "5" pour "URL_SEARCH_MISC"
        else:
            sCat = 1000 # valeur incohrente #todo trouver un moyen pour gerer une mutiple recherche peut-être ?

        sCat += 1000 # ajout 1000 pour distingue un appel kodi d'un appel stremIO

        return title, str(sCat)  # Retourne le titre du film et scat
    else:
        return ""


def contructRqst(requestId):
    bSeriesRqst = False
    nSaison = 'NA'
    nEpisode = 'NA'

    if ":" in requestId:
        bSeriesRqst = True
        requestId, nSaison, nEpisode = requestId.split(":")

    sTitre, sCat = obtenirTitreFilm(requestId)

    return sTitre, bSeriesRqst, nSaison, nEpisode, sCat


def callTraitementWebSite(args):
    requestId, bSeriesRqst, nSaison, nEpisode, sysArg = args
    cmd_args = [requestId, ('1' if bSeriesRqst else '0'), nSaison, nEpisode, "\"" + sysArg + "\""]
    # Récupère le chemin absolu du script courant
    script_path = os.path.abspath(__file__)
    # Récupère le répertoire contenant ce script
    script_dir = os.path.dirname(script_path) + '\\'
    result = subprocess.run(['python', script_dir + 'Traitement_Web_Site.py'] + cmd_args, capture_output=True, text=True)
    output = f"Sortie du processus pour {cmd_args} :\n{result.stdout}"
    try:
        # Utiliser `ast.literal_eval` pour convertir `stdout` en une liste Python
        output_list = ast.literal_eval(result.stdout.strip())
    except (SyntaxError, ValueError) as e:
        if __DEBUG__:
            print(f"Erreur de parsing de result.stdout pour {cmd_args} : {e}")
        output_list = []

    if __DEBUG__ and result.stderr:
        print(f"Erreur du processus pour {cmd_args} :\n{result.stderr}")

    return output_list


def main():
    if len(sys.argv) == 3:
        requestId = sys.argv[1]
        sTitre, bSeriesRqst, nSaison, nEpisode, sCat = contructRqst(requestId)

        sSearchText = sTitre
        oSearch = cSearch()
        oSearch.searchGlobal(sSearchText=sSearchText, sCat=sCat)
        stored_items = xbmcplugin.getDirectoryItems()  # Retourne la liste de tous les sites avec et sans résultats

        # Filtrer les éléments inutilisables
        stored_items = [item for item in stored_items if "cHome" not in item[0] and "DoNothing" not in item[0]]

        # Exécuter les traitements en parallèle avec ProcessPoolExecutor
        args_list = [(requestId, bSeriesRqst, nSaison, nEpisode, item[0]) for item in stored_items]
        with ProcessPoolExecutor(max_workers=len(args_list)) as executor:
            results = executor.map(callTraitementWebSite, args_list)

        # get les resultat et les organiser
        final_list = []
        for output_list in results:
            if output_list:
                final_list.extend(output_list)

        print(final_list)
    else:
        # Cas où il y a trop d'arguments
        print("Erreur: attendu un seul argument sous la forme \"id:imdb\".")
        sys.exit(1)


if __name__ == "__main__":
    main()
