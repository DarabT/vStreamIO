# -*- coding: utf-8 -*-
# Ajout des chemin vers sources
import sys  # to comunicate with node.js
import os
import sqlite3
import re
import threading
from concurrent.futures import ThreadPoolExecutor
import types
from contextlib import contextmanager

path = os.path.realpath(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(path))
db_name = ""

max_workers_ThreadPoolExecutor = 0 # Valeur pardéfaut = 0 (on utlise autant de coeur que possible). sinon utilisé une valeur fix
if max_workers_ThreadPoolExecutor == 0:
    max_workers_ThreadPoolExecutor = os.cpu_count() or 4 #valeur de repli = 4
    max_workers_ThreadPoolExecutor = max_workers_ThreadPoolExecutor*2

import import_paths
import_paths.setup_paths()

import xbmcplugin
import addonPythonScript.Thread_argv as Thread_argv


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
bInitlock = threading.Lock()
requestId = ''
bSeriesRqst = False
nSaison = 0
nEpisode = 0

def callvStream():
    from default import main as vStreamMain
    global bInit

    if bInit:
        with bInitlock:
            if bInit:
                bInit = False # no need to call le import appel deja la fonction main
            else:
                vStreamMain()
    else:
        vStreamMain()

    return

def vStreamCapsul(args):
    bLastTraitement = False
    new_arguments = args[0][0]
    if new_arguments.startswith('"') and new_arguments.endswith('"'):
        new_arguments = new_arguments[1:-1]
    path, separator, params = new_arguments.partition('?')
    params = separator + params
    if "&function=play&" in params:
        ajouterElementDB(args[1], args[2], args[3], args[4], args[5], args[0], args[6]) #save dans la DB
        bLastTraitement = True
        params = re.sub(r'&sCat=\d+&', '&sCat=9999&', params) #remplace pour save dans la bonne tab de sortie

    fake_argv = ["TOTO.py", path, params]

    # Définir sys.argv pour ce thread
    Thread_argv.set_custom_argv(fake_argv)

    callvStream()

    return bLastTraitement

def getWebSiteNameAndSiteUrl(stored_items):
    nomDuSite = None
    siteUrl = None # pour regler le cas des doublons

    for item in stored_items:
        site_match = re.search(r"site=([^&]+)", item[0])
        site_url_match = re.search(r"siteUrl=([^&]+)", item[0])

        if site_match:
            nomDuSite = site_match.group(1) # on recup le nom du site (et db)

        if site_url_match:
            raw_url = site_url_match.group(1) # on recup la case siteUrl au complet
            parts = raw_url.split('%2F') # on extrait tout ce qui %2F => /
            if len(parts) >= 4:
                # Recolle tout après le 3ème %2F (/) pour ne pas etre impacter par le cas d'un changement du nom ou .com .org ... etc du site
                siteUrl = '%2F' + '%2F'.join(parts[3:])

        if nomDuSite and siteUrl:
            break

    return nomDuSite, siteUrl

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
                                stored_items TEXT,
                                siteUrl TEXT
                            )
                        ''')
            conn.close()
        else:
            b_db_already_exist = True
    return b_db_already_exist

def ajouterElementDB(db_name, requestId, bSeriesRqst, nSaison, nEpisode, stored_items, siteUrl):
    b_Return = False
    # Connexion à la base de données
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Insertion des données dans la table
    try:
        cursor.execute('''
            INSERT INTO requests (requestId, bSeriesRqst, nSaison, nEpisode, stored_items, siteUrl)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (requestId, int(bSeriesRqst), nSaison, nEpisode, str(stored_items), siteUrl))

        conn.commit()  # Valider la transaction
        b_Return = True
    except sqlite3.Error as e:
        # print(f"Erreur lors de l'ajout de l'élément : {e}")
        b_Return = False
    finally:
        conn.close()  # Fermer la connexion

    return b_Return

def rechercherElementsDB(requestId, bSeriesRqst, nSaison, nEpisode, bMainRqstNewSearch, siteUrl):
    global db_name

    b_Return = False
    b_SameSeriesDiffrentSaisonOrEp = False
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
                WHERE requestId = ? AND bSeriesRqst = ? AND nSaison = ? AND nEpisode = ? AND siteUrl = ?
            ''', (requestId, int(bSeriesRqst), nSaison, nEpisode, siteUrl))

            # Récupérer les résultats
            resultats = cursor.fetchall()

            if (not resultats) and bSeriesRqst: #cas possible dans le cas ou la premiere recherche avait etait avec une saison differente
                # Rechercher les lignes correspondantes
                cursor.execute('''
                                SELECT stored_items FROM requests
                                WHERE requestId = ? AND bSeriesRqst = ? AND nSaison = ? AND nEpisode = ? AND siteUrl = ?
                            ''', (requestId, int(bSeriesRqst), nSaison, str(0), siteUrl)) #ep 0

                # Récupérer les résultats
                resultats = cursor.fetchall()
                b_SameSeriesDiffrentSaisonOrEp = True

            if resultats:
                # Extraire les stored_items des lignes correspondantes
                nouveau_resultats = []
                for item in resultats:
                    match = re.search(r"\('(.+?)', <", item[0])
                    if match:
                        extrait = match.group(1)  # On extrait la partie souhaitée
                        nouveau_resultats.append((extrait, False, False))
                    else:
                        match = re.search(r"\('(.+?)', False, False", item[0])
                        if match:
                            extrait = match.group(1)  # On extrait la partie souhaitée
                            nouveau_resultats.append((extrait, False, False))

                #TODO if nouveau_resultats [] => erreur !!!!!
                #clean des lignes utilisé
                cursor.execute('''
                                DELETE FROM requests
                                WHERE requestId = ? AND bSeriesRqst = ? AND nSaison = ? AND nEpisode = ? AND siteUrl = ?
                                ''', (requestId, int(bSeriesRqst), nSaison, nEpisode, siteUrl))
                if b_SameSeriesDiffrentSaisonOrEp:
                    cursor.execute('''
                                                    DELETE FROM requests
                                                    WHERE requestId = ? AND bSeriesRqst = ? AND nSaison = ? AND nEpisode = ? AND siteUrl = ?
                                                    ''', (requestId, int(bSeriesRqst), nSaison, str(0), siteUrl)) #ep 0
                conn.commit()
                b_Return = True
            else:
                cursor.execute('''
                                SELECT stored_items FROM requests
                                WHERE requestId = ? AND bSeriesRqst = ? AND siteUrl = ?
                                ''', (requestId, int(bSeriesRqst), siteUrl))  # ep 0
                resultats = cursor.fetchall()
                if (resultats):
                    #on deja recu une rqst de cette page web et ce n'etait pas la bonne saison. => Cas de plusieurs pages pour le même site
                    b_Return = True # on ne fait rien avec cette page
                    # Exemple de cas, https:\\site\Serie\saison_1 + https:\\site\Serie\saison_2. La recherche nous donne deux pages web (une pour chaque saison)
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

        requestId, bSeriesRqst, nSaison, nEpisode, stored_items, bMainRqstNewSearch = getContructRqst()

        nomDuSite, siteUrl = getWebSiteNameAndSiteUrl(stored_items)
        bcheckdbbefore = initDB(nomDuSite)

        const_info_db_play = (db_name, requestId, bSeriesRqst, nSaison, nEpisode, siteUrl)

        if bcheckdbbefore:
            #la base db exist deja checker si la recherche a etait deja faite d'abord
            bOldSearchMatched, OldListedMatched = rechercherElementsDB(requestId, bSeriesRqst, nSaison, nEpisode, bMainRqstNewSearch, siteUrl)
            if bOldSearchMatched and bMainRqstNewSearch == False:
                stored_items = OldListedMatched

        while(bLastTraitement == False and len(stored_items)):
            if bSeriesRqst:  # catch le lien vers la bonne saison et le bon episode
                nSaisonOfLine, nEpisodeOfLine = 0, 0
                for i in range(len(stored_items) - 1, -1, -1):
                    bFlagPopByEp = False
                    bFlagPopBySaison = False
                    new_arguemnts = stored_items[i][0]
                    saison_match = re.search(r"sSeason=(\d+)", new_arguemnts)
                    episode_match = re.search(r"sEpisode=(\d+)", new_arguemnts)
                    if saison_match:
                        nSaisonOfLine = int(saison_match.group(1)) if saison_match else None
                        if not (int(nSaison) == nSaisonOfLine):
                            bFlagPopBySaison = True # ce n'est pas la saison rechercher
                        else:
                            bFlagPopBySaison = False # c'est la bonne saison

                    if episode_match:
                        nEpisodeOfLine = int(episode_match.group(1)) if episode_match else None
                        if not (int(nEpisode) == nEpisodeOfLine):
                            bFlagPopByEp = True # ce n'est pas l'ep rechercher
                    if bFlagPopByEp or bFlagPopBySaison:
                        ajouterElementDB(db_name, requestId, bSeriesRqst, nSaisonOfLine if bFlagPopBySaison else nSaison, nEpisodeOfLine, stored_items[i], siteUrl)    #avant de pop l'element on vient le save dans le db, pour repartir de ce point si recherche similaire (differente saison ou diffrent ep)
                        stored_items.pop(i) #on a bien trouver les deux infos n°Saison et n°Episode mais elle ne match pas (on l'eclu de la liste)

            # Preparation des arg pour exécution en parallèle avec ProcessPoolExecutor
            args_list = [(item, *const_info_db_play) for item in stored_items]

            #print("DEBUG stored_items:", stored_items)

            if len(stored_items) != 0:
                with ThreadPoolExecutor(max_workers=min(max_workers_ThreadPoolExecutor, len(stored_items))) as executor:
                    bLastTraitement = list(executor.map(vStreamCapsul, args_list)) #TODO cas ou bLastTraitement serait en decalage sur plusieurs appel possible ? Ex: une etape est deja au play mais pas les autres

                if any(bLastTraitement):  # si un des appel est en mode "function=play"
                    bLastTraitement = True
                else:
                    bLastTraitement = False
            else:
                bLastTraitement = True

            stored_items = xbmcplugin.getDirectoryItems()
            xbmcplugin.clearDirectoryItems()


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
