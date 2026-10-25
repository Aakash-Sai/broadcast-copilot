"""Create a source-only hosting archive from an explicit allowlist. No credentials."""
import hashlib
import tarfile
from pathlib import Path


def package(destination=None):
    root=Path(__file__).resolve().parent.parent
    destination=Path(destination) if destination else root/'runtime/release/broadcast-hosting.tar.gz'
    files=[root/name for name in ['Dockerfile','.dockerignore','compose.azure.yaml','package.json',
        'pnpm-lock.yaml','pnpm-workspace.yaml','tsconfig.json','vite.config.ts','requirements.lock.txt','scripts/backup_editorial.py']]
    for directory in ['frontend','backend','data','deploy/azure']:
        files.extend(path for path in (root/directory).rglob('*') if path.is_file()
            and '__pycache__' not in path.parts and not path.name.endswith('.pyc') and not path.name.startswith('.env'))
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(destination,'w:gz') as archive:
        for file in sorted(files):
            if not file.resolve().is_relative_to(root):
                raise ValueError('Hosting package cannot contain files outside the workspace.')
            archive.add(file,arcname=file.relative_to(root).as_posix(),recursive=False)
    checksum=hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix+'.sha256').write_text(checksum+'\n',encoding='utf-8')
    return destination,checksum


if __name__=='__main__':
    destination,checksum=package()
    print(f'Created {destination.name}; SHA256 {checksum}')
