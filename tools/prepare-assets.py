import json
import os
import shutil
import subprocess
from pathlib import Path
from re import search

ci = os.environ.get('CI', False)

path_root = Path(__file__).resolve().parent.parent
path_bake = path_root / 'bake'
path_assets = path_root / 'release_assets' if ci else path_root / '.local/release_assets'

# Get CLI version
with open(path_bake / 'setup.py', 'r') as f:
    for line in f:
        if line.startswith('VERSION'):
            txt = str(line).rstrip()
            match = search(r'VERSION = [\'\"](.*)[\'\"]$', txt)
            if match:
                cli_version = match.group(1)
                cli_name = 'bake-{}-py3-none-any.whl'.format(cli_version)

version = f'v{cli_version}'
download_url = f'https://github.com/colbylwilliams/az-bake/releases/download/{version}' if ci else path_assets

index = {}
index['extensions'] = {
    'bake': [
        {
            'downloadUrl': f'{download_url}/{cli_name}',
            'filename': f'{cli_name}',
            'metadata': {
                'azext.isPreview': True,
                'azext.isExperimental': True,
                'azext.minCliCoreVersion': '2.40.0',
                'azext.maxCliCoreVersion': '3.0.0',
                'classifiers': [
                    'Development Status :: 4 - Beta',
                    'Intended Audience :: Developers',
                    'Intended Audience :: System Administrators',
                    'Programming Language :: Python',
                    'Programming Language :: Python :: 3',
                    'Programming Language :: Python :: 3.7',
                    'Programming Language :: Python :: 3.8',
                    'Programming Language :: Python :: 3.9',
                    'Programming Language :: Python :: 3.10',
                    'License :: OSI Approved :: MIT License',
                ],
                'extensions': {
                    'python.details': {
                        'contacts': [
                            {
                                'email': 'colbyw@microsoft.com',
                                'name': 'Microsoft Corporation',
                                'role': 'author'
                            }
                        ],
                        'document_names': {
                            'description': 'DESCRIPTION.rst'
                        },
                        'project_urls': {
                            'Home': 'https://github.com/colbylwilliams/az-bake'
                        }
                    }
                },
                'generator': 'bdist_wheel (0.30.0)',
                'license': 'MIT',
                'metadata_version': '2.0',
                'name': 'bake',
                'summary': 'Microsoft Azure Command-Line Tools Custom Image Helper Extension',
                'version': f'{cli_version}'
            }
        }
    ]
}

# save index.json to assets folder
with open(f'{path_assets}/index.json', 'w') as f:
    json.dump(index, f, ensure_ascii=False, indent=4, sort_keys=True)


path_templates = path_assets / 'templates'

# copy the templates folder to assets folder
shutil.copytree(path_bake / 'azext_bake' / 'templates', path_templates, dirs_exist_ok=not ci)

bicep_templates = []
templates = {}


# walk the templates directory and find all the bicep files
for dirpath, dirnames, files in os.walk(path_templates):
    # os.walk includes the root directory (i.e. assets/templates) so we need to skip it
    if not path_templates.samefile(dirpath) and Path(dirpath).parent.samefile(path_templates):
        bicep_templates.extend([Path(dirpath) / f for f in files if f.lower().endswith('.bicep')])

# for each bicep file, compile it to json
for bicep_template in bicep_templates:
    print('Compiling template: {}'.format(bicep_template))
    subprocess.run(['az', 'bicep', 'build', '-f', bicep_template])


# walk the templates directory find all directories and files and add them to the templates index
for dirpath, dirnames, files in os.walk(path_templates):
    # os.walk includes the root directory (i.e. repo/templates) so we need to skip it
    if not path_templates.samefile(dirpath) and Path(dirpath).parent.samefile(path_templates):
        templates[Path(dirpath).name] = {}
        for f in files:
            templates[Path(dirpath).name][f] = {
                'downloadUrl': f'{download_url}/{f}',
            }

# finally add all the files to the root of the assets folder
for dirpath, dirnames, files in os.walk(path_templates):
    # os.walk includes the root directory (i.e. repo/templates) so we need to skip it
    if not path_templates.samefile(dirpath) and Path(dirpath).parent.samefile(path_templates):
        for f in files:
            shutil.copy2(Path(dirpath) / f, path_assets)

# save templates.json to assets folder
with open(f'{path_assets}/templates.json', 'w') as f:
    json.dump(templates, f, ensure_ascii=False, indent=4, sort_keys=True)


# copy the bake and image schemas to assets folder
shutil.copy2(path_root / 'schemas' / 'bake.schema.json', path_assets)
shutil.copy2(path_root / 'schemas' / 'image.schema.json', path_assets)

assets = []

# add all the files in the root of the assets folder to the assets list
with os.scandir(path_assets) as s:
    for f in s:
        if f.is_file():
            print(f.path)
            # name = f.name.rsplit('.', 1)[0]
            assets.append({'name': f.name, 'path': f.path})


if not ci:  # if working locally, print the assets.json to a file
    with open(f'{path_assets}/assets.json', 'w') as f:
        json.dump(assets, f, ensure_ascii=False, indent=4, sort_keys=True)


github_output = os.environ.get('GITHUB_OUTPUT', None)
if github_output:
    with open(github_output, 'a+') as f:
        f.write(f'assets={json.dumps(assets)}')
