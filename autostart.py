"""可选的当前用户登录启动项；支持源码与便携 EXE，不在导入时改设置。"""
import json
from pathlib import Path
import subprocess
import sys
import winreg

ROOT=(Path(sys.executable).resolve().parent if getattr(sys,'frozen',False)
      else Path(__file__).resolve().parent)
KEY=r'Software\Microsoft\Windows\CurrentVersion\Run'
NAME='CodexQuotaWidget'
BACKUP=ROOT/'runtime'/'autostart-backup.json'


def startup_command():
    if getattr(sys,'frozen',False):
        args=[str(Path(sys.executable).resolve())]
    else:
        args=[str(Path(sys.executable).with_name('pythonw.exe')),'-B',str(ROOT/'widget.py')]
    return subprocess.list2cmdline(args)


def current():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as key:
            value,kind=winreg.QueryValueEx(key,NAME)
            return {'exists':True,'value':value,'type':kind}
    except FileNotFoundError:
        return {'exists':False,'value':None,'type':None}


def configure(action):
    command=startup_command()
    if action=='enable':
        if len(command)>260:
            raise RuntimeError('Startup path is too long. Move the widget to a shorter path.')
        if not BACKUP.exists():
            BACKUP.parent.mkdir(parents=True,exist_ok=True)
            BACKUP.write_text(json.dumps(current(),ensure_ascii=False,indent=2),encoding='utf-8')
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,KEY,0,winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key,NAME,0,winreg.REG_SZ,command)
        if current()['value']!=command:
            raise RuntimeError('Startup registration could not be verified.')
    elif action=='disable':
        now=current()
        if now['exists'] and now['value']!=command:
            raise RuntimeError('Startup entry belongs to another installation; leaving it unchanged.')
        old=json.loads(BACKUP.read_text(encoding='utf-8')) if BACKUP.exists() else {'exists':False}
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,KEY,0,winreg.KEY_SET_VALUE) as key:
            if old['exists']:
                winreg.SetValueEx(key,NAME,0,old['type'],old['value'])
            else:
                try:winreg.DeleteValue(key,NAME)
                except FileNotFoundError:pass
    elif action!='status':
        raise RuntimeError('Use enable, disable or status.')
    return {'enabled':current().get('value')==command,'registryValue':NAME}


def main(args=None):
    args=sys.argv[1:] if args is None else args
    if len(args)!=1:
        return 2
    try:
        result=configure(args[0])
    except (RuntimeError,OSError,ValueError) as error:
        if sys.stderr is not None:print(str(error),file=sys.stderr)
        return 1
    if sys.stdout is not None:print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
