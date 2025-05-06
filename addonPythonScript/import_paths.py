import os
import sys

def setup_paths():
    current_file = os.path.abspath(__file__)
    parent_dir = os.path.abspath(os.path.join(current_file, '..', '..'))

    paths_to_add = [
        os.path.join(parent_dir, 'vStreamKodi', 'plugin.video.vstream'),
        os.path.join(parent_dir, 'KodiStub'),
        parent_dir,
    ]

    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)