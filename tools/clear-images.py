from os import walk
from pathlib import Path
from shutil import rmtree

REPO_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = REPO_DIR / 'images'

files_del = []
dirs_del = []

# walk the images directory and find all the child directories
for dirpath, dirnames, files in walk(IMAGES_DIR):
    # os.walk includes the root directory (i.e. repo/images) so we need to skip it
    if not IMAGES_DIR.samefile(dirpath) and Path(dirpath).parent.samefile(IMAGES_DIR):
        files_del.extend([Path(dirpath) / f for f in files if not f.lower() == 'image.yaml' and not f.lower() == 'image.yml'])
        dirs_del.extend([Path(dirpath) / d for d in dirnames])

for f in files_del:
    f.unlink()

for d in dirs_del:
    rmtree(d)
