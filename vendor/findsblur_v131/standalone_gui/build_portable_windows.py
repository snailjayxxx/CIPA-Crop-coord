"""On an authorized Windows PC, build the GUI and local algorithm into one folder.

The original commercial FindsBlur EXE, private JPGs, RAW, and official TXT are
intentionally not part of this distribution. This script is not a release CI.
"""
from __future__ import annotations
from pathlib import Path
import os
import shutil
import subprocess
import sys


def main():
    if sys.platform != 'win32':
        raise RuntimeError('请在 Windows x64 上运行本地便携式构建。')
    root = Path(__file__).resolve().parents[1]
    decoder = root/'_work'/'IJG8c'/'bin'/'ijg8c_rgb_probe.exe'
    if not decoder.is_file():
        raise FileNotFoundError('IJG8c 解码器尚未编译：' + str(decoder))
    from PyInstaller import __version__ as pyinstaller_version
    print('PyInstaller:', pyinstaller_version)
    package = root/'standalone_gui'
    output = root/'_work'/'findsblur_gui_portable'
    output.mkdir(parents=True,exist_ok=True)
    # No user images, reference results, RAW buffers, or the original EXE.
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean',
         '--onedir','--windowed','--name','FindsBlur_Standalone',
         '--distpath',str(output/'dist'),'--workpath',str(output/'build'),
         '--specpath',str(output),
         '--paths',str(root),'--paths',str(root/'phase5'),
         '--add-binary',str(decoder)+os.pathsep+'_work/IJG8c/bin']
    for group in sorted(root.glob('phase[0-9]*'))+[root/'standalone',package]:
        if not group.is_dir():continue
        for p in group.rglob('*.py'):
            if '__pycache__' in p.parts or 'tests' in p.parts:continue
            cmd+=['--add-data',str(p)+os.pathsep+str(p.relative_to(root).parent)]
    cmd+=['--collect-all','scipy','--collect-all','numba',
          '--hidden-import','PIL.Image', '--hidden-import','phase12.accelerated_topology',
          '--hidden-import','standalone.__main__',str(package/'frozen_entry.py')]
    print('Building portable onedir (NO original EXE or personal files)...')
    subprocess.run(cmd,check=True,cwd=str(root))
    app=output/'dist'/'FindsBlur_Standalone'
    exe=app/'FindsBlur_Standalone.exe'
    if not exe.is_file():raise RuntimeError('EXE 未生成：'+str(exe))
    print('Build output:',app)
    print('Copy WHOLE folder including _internal; test 110+113 official TXT samples.')


if __name__=='__main__':main()
