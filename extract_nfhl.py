import zipfile
import os
import pathlib

nfhl_dir = r'C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\NFHL'
zip_files = sorted(pathlib.Path(nfhl_dir).glob('*.zip'))
print(f'Found {len(zip_files)} zip files')

failed = []
for i, zf in enumerate(zip_files):
    dest = zf.parent / zf.stem
    dest.mkdir(exist_ok=True)
    try:
        with zipfile.ZipFile(zf, 'r') as z:
            z.extractall(dest)
        print(f'[{i+1}/{len(zip_files)}] {zf.name} - OK')
    except Exception as e:
        print(f'[{i+1}/{len(zip_files)}] {zf.name} - FAILED: {e}')
        failed.append(zf.name)

print(f'\nDone. Failed: {len(failed)}')
if failed:
    print('Failed files:', failed[:5])
