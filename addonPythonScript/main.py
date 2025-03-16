# -*- coding: utf-8 -*-
# Ajout des chemins vers sources
import sys  # to communicate with node.js
import os
import ast
import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from imdb import IMDb
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

__DEBUG__ = False
max_workers_ProcessPoolExecutor = 0 # Valeur pardéfaut = 0 (on utlise autant de coeur que possible). sinon utilisé une valeur fix
if max_workers_ProcessPoolExecutor == 0:
    max_workers_ProcessPoolExecutor = os.cpu_count() or 4 #valeur de repli = 4


path = os.path.realpath(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(path))

db_name = "" #path db historique

if (parent_dir + '/vStreamKodi/plugin.video.vstream') not in sys.path:
    sys.path.insert(0, parent_dir + '/vStreamKodi/plugin.video.vstream')
if (parent_dir + '/KodiStub') not in sys.path:
    sys.path.insert(0, parent_dir + '/KodiStub')

from resources.lib.search import cSearch
import xbmcplugin


################################## IMDb incapable de me dire si c'est un anime ou pas utilisation de BeautifulSoup pour catch les Tags et vérfier si "anime" est dedans ##########################################
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


def contructRqst(requestId, sTitre, sCat):
    bSeriesRqst = False
    nSaison = 'NA'
    nEpisode = 'NA'

    if ":" in requestId:
        bSeriesRqst = True
        requestId, nSaison, nEpisode = requestId.split(":")

    if sTitre == '' or sCat == '': # Si on a pas recup deja l'info de la db history
        sTitre, sCat = obtenirTitreFilm(requestId)

    return sTitre, bSeriesRqst, nSaison, nEpisode, sCat


def callTraitementWebSite(args):
    from Traitement_Web_Site import main_Traitement_Web_Site
    requestId, bSeriesRqst, nSaison, nEpisode, sysArg, bMainRqstNewSearch = args
    sysArg = "\"" + sysArg + "\""
    args = ['', requestId, bSeriesRqst, nSaison, nEpisode, sysArg, bMainRqstNewSearch]
    output_list = main_Traitement_Web_Site(args)
    return output_list

def initDB(nomDb):
    global parent_dir
    global db_name
    b_db_already_exist = False
    db_dir = f"{parent_dir}/db/"
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    if nomDb:
        db_name = f"{db_dir}{nomDb}.db"
        if not os.path.exists(db_name):
            # print(f"Création de la base de données : {db_name}")
            conn = sqlite3.connect(db_name)
            cursor = conn.cursor()
            cursor.execute('''
                            CREATE TABLE IF NOT EXISTS requests (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                DT DATETIME DEFAULT CURRENT_TIMESTAMP,
                                requestId TEXT,
                                cleanRequestId TEXT,
                                title TEXT,
                                args_list TEXT,
                                NewSearch INTEGER,
                                CAT INTEGER
                            )
                        ''')
            conn.close()
        else:
            b_db_already_exist = True
    return b_db_already_exist

def getIfNeedNewSearchDB(requestId):
    global db_name
    #return
    bNeedNewSearch = True
    title = ''
    args_list = []
    Cat = 0

    # Connexion à la base de données
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    if ":" in requestId:
        #serie
        cleanRequestId, nSaison, nEpisode = requestId.split(":")
    else:
        #movie
        cleanRequestId = requestId

    try:
        # Rechercher les lignes correspondantes
        cursor.execute('''
            SELECT * FROM requests
            WHERE requestId = ?
            ORDER BY DT DESC
            LIMIT 1
        ''', (requestId,))

        # Récupérer les résultats
        LastRqstDone = cursor.fetchone() #peu importe si c'etait une vrai recherche ou pas

        cursor.execute('''
            SELECT * FROM requests
            WHERE cleanRequestId = ? AND NewSearch = 1
            ORDER BY DT DESC
            LIMIT 1
        ''', (cleanRequestId,))

        LastSearchDone = cursor.fetchone()  #La dernier recherche realement effectué
        conn.close()  # Fermer la connexion

        #Tester le detla du temps
        maintenant = datetime.now()
        if LastRqstDone:
            LastRqstDoneTime = datetime.strptime(LastRqstDone[1], "%Y-%m-%d %H:%M:%S")  # Convertit en objet datetime
            title = LastSearchDone[4]  # Index de la colonne title
            Cat = LastSearchDone[7]  # Index de la colonne CAT

            if timedelta(minutes=1) < (maintenant - LastRqstDoneTime):
                if LastSearchDone:
                    LastSearchDoneTime = datetime.strptime(LastSearchDone[1],
                                                         "%Y-%m-%d %H:%M:%S")  # Convertit en objet datetime
                    if (maintenant - LastSearchDoneTime) < timedelta(days=7):
                        #recherche assez récente
                        args_list = LastSearchDone[5]  # Index de la colonne args_list
                        args_list = ast.literal_eval(args_list)
                        bNeedNewSearch = False # la dernier recherche avec exactement le meme id remonte à plus de 1min et la dernier vrai recherche faite remonte à moins de 7jours
                    else:
                        bNeedNewSearch = True # recherche trop vielle relancé une nouvelle recherche
                else:
                    bNeedNewSearch = True #cas theoriquement impossible mais bon why not
            else:
                # Rqst de forcage recherche
                bNeedNewSearch = True
        else:
            # Aucune ligne correspondante trouvée
            bNeedNewSearch = True
    except sqlite3.Error as e:
        # print(f"Erreur lors de la recherche dans la base de données : {e}")
        bNeedNewSearch = True
    finally:
        conn.close()  # Fermer la connexion

    return bNeedNewSearch, title, args_list, str(Cat)

def ajouterElementDB(requestId, title, args_list, bNewSearch, sCat):
    global db_name
    # Connexion à la base de données
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    if ":" in requestId:
        #serie
        cleanRequestId, nSaison, nEpisode = requestId.split(":")
    else:
        #movie
        cleanRequestId = requestId
    # Insertion des données dans la table
    try:
        local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Heure locale
        cursor.execute('''
            INSERT INTO requests (DT, requestId, cleanRequestId, title, args_list, NewSearch, CAT)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (local_time, requestId, cleanRequestId, title, str(args_list), int(bNewSearch), int(sCat)))

        conn.commit()  # Valider la transaction
        return True
    except sqlite3.Error as e:
        # print(f"Erreur lors de l'ajout de l'élément : {e}")
        return False
    finally:
        conn.close()  # Fermer la connexion

def main():
    if len(sys.argv) == 3:
        requestId = sys.argv[1]
        args_list = []
        bcheckdbbefore = initDB("historique")
        bNeedNewSearch = True
        sTitre = ''
        sCat = ''

        if bcheckdbbefore:
            bNeedNewSearch, sTitre, args_list, sCat = getIfNeedNewSearchDB(requestId)

        if bNeedNewSearch == True:
            #nouvelle rqst ou demande de maj
            sTitre, bSeriesRqst, nSaison, nEpisode, sCat = contructRqst(requestId, sTitre, sCat)

            sSearchText = sTitre
            oSearch = cSearch()
            oSearch.searchGlobal(sSearchText=sSearchText, sCat=sCat)
            stored_items = xbmcplugin.getDirectoryItems()  # Retourne la liste de tous les sites avec et sans résultats

            # Filtrer les éléments inutilisables
            stored_items = [item for item in stored_items if "cHome" not in item[0] and "DoNothing" not in item[0]]

            # Preparation des arg pour exécution en parallèle avec ProcessPoolExecutor
            args_list = [(requestId, bSeriesRqst, nSaison, nEpisode, item[0]) for item in stored_items]
        #else:
            # utilisation du dernier resultat de recherche

        # le save dans la db
        ajouterElementDB(requestId, sTitre, args_list, bNeedNewSearch, sCat)
        # Ajout booleen pour indiquer aux sous script s'il faut forcer une nouvelle recherche
        args_list = [item + (bNeedNewSearch,) for item in args_list]

        with ProcessPoolExecutor(max_workers=min(max_workers_ProcessPoolExecutor, len(args_list)) )as executor:
            results = executor.map(callTraitementWebSite, args_list)

        # get les resultat et les organiser
        final_list = []
        for output_list in results:
            if output_list:
                final_list.extend(output_list)

        final_list.sort()
        print(final_list)
    else:
        # Cas où il y a trop d'arguments
        print("Erreur: attendu un seul argument sous la forme \"id:imdb\".")
        sys.exit(1)


if __name__ == "__main__":
    main()
