"""构建 Windows x64 目录版；不打包 Codex、凭据或本机运行数据。"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build'
DIST=ROOT/'dist'
if not DIST.resolve().is_relative_to(ROOT.resolve()):
    raise RuntimeError('Build output must stay inside the project directory.')
(BUILD/'tmp').mkdir(parents=True,exist_ok=True)
env=os.environ.copy()
env.update(TEMP=str(BUILD/'tmp'),TMP=str(BUILD/'tmp'),
 PYINSTALLER_CONFIG_DIR=str(BUILD/'pyinstaller-cache'),PYTHONDONTWRITEBYTECODE='1')
subprocess.check_call([sys.executable,'-B','-m','PyInstaller','--noconfirm','--onedir','--windowed',
 '--noupx','--name','CodexQuotaWidget','--distpath',str(DIST),'--workpath',str(BUILD/'work'),
 '--specpath',str(BUILD),'--paths',str(ROOT/'lib'),'--copy-metadata','Pillow',str(ROOT/'widget.py')],cwd=ROOT,env=env)
package=DIST/'CodexQuotaWidget'
for name in ('README.md','LICENSE','THIRD_PARTY_NOTICES.md','enable-autostart.cmd','disable-autostart.cmd'):
 shutil.copy2(ROOT/name,package/name)
shutil.copytree(ROOT/'docs'/'images',package/'docs'/'images',dirs_exist_ok=True)
shutil.copytree(ROOT/'docs'/'licenses',package/'licenses',dirs_exist_ok=True)
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():shutil.copy2(python_license,package/'licenses'/'PYTHON-LICENSE.txt')
print('Built portable folder:',package)
