import json
import os
import subprocess
from pathlib import Path
from re import search

ci = os.environ.get('CI', False)

path_root = Path(__file__).resolve().parent.parent
path_assets = path_root / 'release_assets' if ci else '.local/release_assets'

path_bake = path_root / 'bake'
path_templates = path_root / 'templates'

assets = []

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

with open(f'{path_assets}/index.json', 'w') as f:
    json.dump(index, f, ensure_ascii=False, indent=4, sort_keys=True)


bicep_templates = []

templates = {}

# walk the templates directory and find all the bicep files
for dirpath, dirnames, files in os.walk(path_templates):
    # os.walk includes the root directory (i.e. repo/templates) so we need to skip it
    if not path_templates.samefile(dirpath) and Path(dirpath).parent.samefile(path_templates):
        bicep_templates.extend([Path(dirpath) / f for f in files if f.lower().endswith('.bicep')])

for bicep_template in bicep_templates:
    print('Compiling template: {}'.format(bicep_template))
    subprocess.run(['az', 'bicep', 'build', '-f', bicep_template, '--outdir', path_assets])


# walk the templates directory and find all the bicep files
for dirpath, dirnames, files in os.walk(path_templates):
    # os.walk includes the root directory (i.e. repo/templates) so we need to skip it
    if not path_templates.samefile(dirpath) and Path(dirpath).parent.samefile(path_templates):
        templates[Path(dirpath).name] = {}
        for f in files:
            templates[Path(dirpath).name][f] = {
                'downloadUrl': f'{download_url}/{f.replace(".bicep", ".json")}',
            }

# print(json.dumps(templates, indent=4))

with open(f'{path_assets}/templates.json', 'w') as f:
    json.dump(templates, f, ensure_ascii=False, indent=4, sort_keys=True)


with os.scandir(path_assets) as s:
    for f in s:
        if f.is_file():
            print(f.path)
            name = f.name.rsplit('.', 1)[0]
            assets.append({'name': f.name, 'path': f.path})


if not ci:  # if working locally, print the assets.json to a file
    with open(f'{path_assets}/assets.json', 'w') as f:
        json.dump(assets, f, ensure_ascii=False, indent=4, sort_keys=True)

print("::set-output name=assets::{}".format(json.dumps(assets)))
