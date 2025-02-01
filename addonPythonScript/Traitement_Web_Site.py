# -*- coding: utf-8 -*-
# Ajout des chemin vers sources
import sys  # to comunicate with node.js
import os.path

path = os.path.realpath(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(path))
if (parent_dir + '\\vStreamKodi\\plugin.video.vstream') not in sys.path:
    sys.path.insert(0, parent_dir + '\\vStreamKodi\\plugin.video.vstream')
if (parent_dir + '\\KodiStub') not in sys.path:
    sys.path.insert(0, parent_dir + '\\KodiStub')

import re
import xbmcplugin

def getContructRqst():
    bSeriesRqst = int(sys.argv[1])
    nSaison = sys.argv[2]
    nEpisode = sys.argv[3]
    sysArg = sys.argv[4]

    return bSeriesRqst, nSaison, nEpisode, [(sysArg, False, False)]

bInit = True
def callvStream():
    from default import main as vStreamMain
    global bInit
    if bInit:
        bInit = False
    else:
        vStreamMain()
    #no need to call le import appel deja la fonction main

def main():
    # Vérification des arguments passés au script
    if len(sys.argv) == 5:
        bSeriesRqst, nSaison, nEpisode, stored_items = getContructRqst()

        bLastTraitement = False
        bSaisonAndEpisodCatched = False
        bSaisonCatched = False
        while(bLastTraitement == False and len(stored_items)):
            if bSeriesRqst and not bSaisonAndEpisodCatched:  # catch le lien vers la bonne saison et le bon episode
                for i in range(len(stored_items) - 1, -1, -1):
                    bFlagPop = False
                    new_arguemnts = stored_items[i][0]
                    saison_match = re.search(r"sSeason=(\d+)", new_arguemnts)
                    episode_match = re.search(r"sEpisode=(\d+)", new_arguemnts)
                    if saison_match and not bSaisonCatched:
                        nSaisonOfLine = int(saison_match.group(1)) if saison_match else None
                        if not (int(nSaison) == nSaisonOfLine):
                            bFlagPop = True
                        else:
                            bSaisonCatched = True
                    if episode_match:
                        nEpisodeOfLine = int(episode_match.group(1)) if episode_match else None
                        if not (int(nEpisode) == nEpisodeOfLine):
                            bFlagPop = True #flag pour indiquer qu'il n'est plus n'ecessaire d'essayer de matcher saison/ep
                    if bFlagPop:
                        stored_items.pop(i) #on a bien trouver les deux infos n°Saison et n°Episode mais elle ne match pas (on l'eclu de la liste)

            xbmcplugin.clearDirectoryItems()
            for stored_item in stored_items:
                new_arguemnts = stored_item[0]
                path, separator, params = new_arguemnts.partition('?')
                params = separator + params  # Reconstruire params pour inclure le '?'
                if "function=play" in params:
                    bLastTraitement = True
                    params = re.sub(r'&sCat=\d+&', '&sCat=9999&', params)
                sys.argv = ["TOTO.py", path, params]
                callvStream()
            stored_items = xbmcplugin.getDirectoryItems()
    else:
        # Cas où il y a trop d'arguments
        print("Erreur: argument attendu : \"bSeriesRqst, nSaison, nEpisode, stored_items\".")
        sys.exit(1)



if __name__ == "__main__":
    main()
    stored_items = xbmcplugin.getFluxPlayer()
    print(stored_items)
