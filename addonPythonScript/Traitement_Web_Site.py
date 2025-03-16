# -*- coding: utf-8 -*-
# Ajout des chemin vers sources
import sys  # to comunicate with node.js
import os
import sqlite3
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

path = os.path.realpath(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(path))
db_name = ""

thread_local = threading.local()
max_workers_ThreadPoolExecutor = 0 # Valeur pardéfaut = 0 (on utlise autant de coeur que possible). sinon utilisé une valeur fix
if max_workers_ThreadPoolExecutor == 0:
    max_workers_ThreadPoolExecutor = os.cpu_count() or 4 #valeur de repli = 4
    max_workers_ThreadPoolExecutor = max_workers_ThreadPoolExecutor*2

if (parent_dir + '/vStreamKodi/plugin.video.vstream') not in sys.path:
    sys.path.insert(0, parent_dir + '/vStreamKodi/plugin.video.vstream')
if (parent_dir + '/KodiStub') not in sys.path:
    sys.path.insert(0, parent_dir + '/KodiStub')

import xbmcplugin


def getContructRqst():
    requestId = sys.argv[1]
    if ":" in requestId:
        #serie
        requestId, nSaison, nEpisode = requestId.split(":")
    else:
        #movie
        requestId = requestId
        nSaison = 0
        nEpisode = 0
    bSeriesRqst = int(sys.argv[2])
    nSaison = sys.argv[3] #sur ecriture
    nEpisode = sys.argv[4] #sur ecriture
    sysArg = sys.argv[5]
    bMainRqstNewSearch = sys.argv[6]

    return requestId, bSeriesRqst, nSaison, nEpisode, [(sysArg, False, False)], bMainRqstNewSearch
#Global
bInit = True
requestId = ''
bSeriesRqst = False
nSaison = 0
nEpisode = 0

def get_thread_argv():
    """Récupère sys.argv spécifique au thread ou retourne l'original."""
    return getattr(thread_local, "argv", sys.argv)

@contextmanager
def monkey_patched_sys_argv():
    """Remplace temporairement sys.argv par la version thread-local du thread courant."""
    original_sys_argv = sys.argv  # Sauvegarde l'original
    sys.modules["sys"].argv = get_thread_argv()  # Remplace temporairement
    try:
        yield  # Exécute le code avec sys.argv modifié
    except:
        #sys.modules["sys"].argv = original_sys_argv  # Restaure l'original
        pass

def callvStream():
    from default import main as vStreamMain
    global bInit

    if bInit:
        # no need to call le import appel deja la fonction main
        bInit = False
    else:
        vStreamMain()

    return

def vStreamCapsul(args):
    bLastTraitement = False
    new_arguemnts = args[0][0]
    if new_arguemnts.startswith('"') and new_arguemnts.endswith('"'):
        new_arguemnts = new_arguemnts[1:-1]
    path, separator, params = new_arguemnts.partition('?')
    params = separator + params  # Reconstruire params pour inclure le '?'
    if "&function=play&" in params:
        ajouterElementDB(args[1], args[2], args[3], args[4], args[5],
                         args[0])  # save du resultat pour le prochain coup
        bLastTraitement = True
        params = re.sub(r'&sCat=\d+&', '&sCat=9999&', params)
    thread_local.argv = ["TOTO.py", path, params]
    with monkey_patched_sys_argv():
        callvStream()

    #print("callvStream: " + str(xbmcplugin.getFluxPlayer()))
    return bLastTraitement

def getWebSiteName(stored_items):
    nomDuSite = None
    for item in stored_items:
        site_match = re.search(r"site=([^&]+)", item[0])
        if site_match:
            nomDuSite = site_match.group(1) # On récupère le nom de site
            break
    return nomDuSite

def initDB(nomDuSite):
    global parent_dir
    global db_name
    b_db_already_exist = False
    db_dir = f"{parent_dir}/db/"
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    if nomDuSite:
        db_name = f"{db_dir}{nomDuSite}.db"
        if not os.path.exists(db_name):
            # print(f"Création de la base de données : {db_name}")
            conn = sqlite3.connect(db_name)
            cursor = conn.cursor()
            cursor.execute('''
                            CREATE TABLE IF NOT EXISTS requests (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                requestId TEXT,
                                bSeriesRqst INTEGER,
                                nSaison INTEGER,
                                nEpisode INTEGER,
                                stored_items TEXT
                            )
                        ''')
            conn.close()
        else:
            b_db_already_exist = True
    return b_db_already_exist

def ajouterElementDB(db_name, requestId, bSeriesRqst, nSaison, nEpisode, stored_items):
    b_Return = False
    # Connexion à la base de données
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Insertion des données dans la table
    try:
        cursor.execute('''
            INSERT INTO requests (requestId, bSeriesRqst, nSaison, nEpisode, stored_items)
            VALUES (?, ?, ?, ?, ?)
        ''', (requestId, int(bSeriesRqst), nSaison, nEpisode, str(stored_items)))

        conn.commit()  # Valider la transaction
        b_Return = True
    except sqlite3.Error as e:
        # print(f"Erreur lors de l'ajout de l'élément : {e}")
        b_Return = False
    finally:
        conn.close()  # Fermer la connexion

    return b_Return

def rechercherElementsDB(requestId, bSeriesRqst, nSaison, nEpisode, bMainRqstNewSearch):
    global db_name

    b_Return = False
    nouveau_resultats = []

    # Connexion à la base de données
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    try:
        if bMainRqstNewSearch == True:
            # clean des lignes qui vont etre actualisee
            cursor.execute('''
                                    DELETE FROM requests
                                    WHERE requestId = ?
                                    ''', (requestId,))
            conn.commit()
            b_Return = False
            nouveau_resultats = []
        else:
            # Rechercher les lignes correspondantes
            cursor.execute('''
                SELECT stored_items FROM requests
                WHERE requestId = ? AND bSeriesRqst = ? AND nSaison = ? AND nEpisode = ?
            ''', (requestId, int(bSeriesRqst), nSaison, nEpisode))

            # Récupérer les résultats
            resultats = cursor.fetchall()

            if resultats:
                # Extraire les stored_items des lignes correspondantes
                nouveau_resultats = []
                for item in resultats:
                    match = re.search(r"\('(.+?)', <", item[0])
                    if match:
                        extrait = match.group(1)  # On extrait la partie souhaitée
                        nouveau_resultats.append((extrait, False, False))

                #clean des lignes utilisé
                cursor.execute('''
                                DELETE FROM requests
                                WHERE requestId = ? AND bSeriesRqst = ? AND nSaison = ? AND nEpisode = ?
                                ''', (requestId, int(bSeriesRqst), nSaison, nEpisode))
                conn.commit()
                b_Return = True
            else:
                # Aucune ligne correspondante trouvée
                b_Return = False
                nouveau_resultats = []
    except sqlite3.Error as e:
        #print(f"Erreur lors de la recherche dans la base de données : {e}")
        b_Return = False
        nouveau_resultats = []
    finally:
        conn.close()  # Fermer la connexion

    return b_Return, nouveau_resultats

def main():
    global db_name
    # Vérification des arguments passés au script
    if len(sys.argv) == 7:
        global requestId, bSeriesRqst, nSaison, nEpisode
        bLastTraitement = False
        bSaisonAndEpisodCatched = False
        bSaisonCatched = False

        requestId, bSeriesRqst, nSaison, nEpisode, stored_items, bMainRqstNewSearch = getContructRqst()

        nomDuSite = getWebSiteName(stored_items)
        bcheckdbbefore = initDB(nomDuSite)

        const_info_db_play = (db_name, requestId, bSeriesRqst, nSaison, nEpisode)

        if bcheckdbbefore:
            #la base db exist deja checker si la recherche a etait deja faite d'abord
            bOldSearchMatched, OldListedMatched = rechercherElementsDB(requestId, bSeriesRqst, nSaison, nEpisode, bMainRqstNewSearch)
            if bOldSearchMatched and OldListedMatched and bMainRqstNewSearch == False:
                stored_items = OldListedMatched
                bSaisonCatched = True

        while(bLastTraitement == False and len(stored_items)):
            if bSeriesRqst and not bSaisonAndEpisodCatched:  # catch le lien vers la bonne saison et le bon episode
                nSaisonOfLine, nEpisodeOfLine = 0, 0
                for i in range(len(stored_items) - 1, -1, -1):
                    bFlagPop = False
                    new_arguemnts = stored_items[i][0]
                    saison_match = re.search(r"sSeason=(\d+)", new_arguemnts)
                    episode_match = re.search(r"sEpisode=(\d+)", new_arguemnts)
                    if saison_match and not bSaisonCatched:
                        nSaisonOfLine = int(saison_match.group(1)) if saison_match else None
                        if not (int(nSaison) == nSaisonOfLine):
                            bFlagPop = True # ce n'est pas la saison rechercher
                        else:
                            bSaisonCatched = True
                    if episode_match:
                        nEpisodeOfLine = int(episode_match.group(1)) if episode_match else None
                        if not (int(nEpisode) == nEpisodeOfLine):
                            bFlagPop = True # ce n'est pas l'ep rechercher
                    if bFlagPop:
                        ajouterElementDB(db_name, requestId, bSeriesRqst, nSaison if bSaisonCatched else nSaisonOfLine, nEpisodeOfLine, stored_items[i])    #avant de pop l'element on vient le save dans le db, pour repartir de ce point si recherche similaire (differente saison ou diffrent ep)
                        stored_items.pop(i) #on a bien trouver les deux infos n°Saison et n°Episode mais elle ne match pas (on l'eclu de la liste)

            # Preparation des arg pour exécution en parallèle avec ProcessPoolExecutor
            args_list = [(item, *const_info_db_play) for item in stored_items]

            #print("DEBUG stored_items:", stored_items)

            with ThreadPoolExecutor(max_workers=min(max_workers_ThreadPoolExecutor, len(stored_items))) as executor:
                bLastTraitement = list(executor.map(vStreamCapsul, args_list)) #TODO cas ou bLastTraitement serait en decalage sur plusieurs appel possible ? Ex: une etape est deja au play mais pas les autres

            stored_items = xbmcplugin.getDirectoryItems()
            xbmcplugin.clearDirectoryItems()

            if any(bLastTraitement): #si un des appel est en mode "function=play"
                bLastTraitement = True
            else:
                bLastTraitement = False
            #print(str(bLastTraitement) + "   " + str(xbmcplugin.getFluxPlayer()))
    else:
        # Cas où il y a trop d'arguments
        print("Erreur: argument attendu : \"bSeriesRqst, nSaison, nEpisode, stored_items\".")
        sys.exit(1)

def main_Traitement_Web_Site(args):
    sys.argv = args
    main()
    stored_items = xbmcplugin.getFluxPlayer()
    return stored_items
