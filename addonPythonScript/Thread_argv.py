import threading
import sys
# Exemple d'une variable globale (peut être modifiée selon tes besoins)
thread_local = threading.local()

def get_custom_argv():
    try:
        return thread_local.argv
    except:
        return sys.argv

def set_custom_argv(argv):
    thread_local.argv = argv

def set_custom_argv_specif(id, value):
    try:
        thread_local.argv[id] = value
    except:
        sys.argv[id] = value