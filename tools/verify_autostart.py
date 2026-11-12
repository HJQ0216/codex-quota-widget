"""测试自动启动的备份/恢复和后台等待，不改真实 Windows 启动项。"""
from contextlib import contextmanager
import json
from pathlib import Path
import queue
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import autostart
import widget
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'build'/'tmp').mkdir(parents=True,exist_ok=True)
original=autostart.current()

class Registry:
    HKEY_CURRENT_USER='user';KEY_SET_VALUE=2;REG_SZ=1
    def __init__(self):self.values={}
    @contextmanager
    def OpenKey(self,*args):yield self
    @contextmanager
    def CreateKeyEx(self,*args):yield self
    def QueryValueEx(self,key,name):
        if name not in self.values:raise FileNotFoundError(name)
        return self.values[name]
    def SetValueEx(self,key,name,reserved,kind,value):self.values[name]=(value,kind)
    def DeleteValue(self,key,name):
        if name not in self.values:raise FileNotFoundError(name)
        del self.values[name]

with tempfile.TemporaryDirectory(dir=ROOT/'build'/'tmp') as directory:
    temporary=Path(directory).resolve()
    assert temporary.is_relative_to((ROOT/'build').resolve())
    registry=Registry()
    backup=temporary/'state'/'autostart-backup.json'
    with patch.object(autostart,'winreg',registry),patch.object(autostart,'BACKUP',backup):
        assert not autostart.configure('status')['enabled']
        assert autostart.configure('enable')['enabled']
        assert not json.loads(backup.read_text(encoding='utf-8'))['exists']
        assert autostart.configure('enable')['enabled']
        autostart.configure('disable')
        assert not registry.values
        backup.unlink()
        registry.values[autostart.NAME]=('existing-installation-command',1)
        autostart.configure('enable');autostart.configure('disable')
        assert registry.values[autostart.NAME][0]=='existing-installation-command'
        # 另一份安装修改后，撤销不得覆盖它。
        backup.unlink();autostart.configure('enable')
        registry.values[autostart.NAME]=('external-installation-command',1)
        try:autostart.configure('disable')
        except RuntimeError:pass
        else:raise AssertionError('External registry change must be preserved')
        assert registry.values[autostart.NAME][0]=='external-installation-command'
        # 源码与便携 EXE 均正确引用含空格的安装路径。
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',r'D:\Apps With Spaces\CodexQuotaWidget.exe'):
            assert autostart.startup_command()=='"D:\\Apps With Spaces\\CodexQuotaWidget.exe"'
        with patch.object(autostart,'startup_command',return_value='x'*261):
            before=dict(registry.values)
            try:autostart.configure('enable')
            except RuntimeError:pass
            else:raise AssertionError('Too-long paths must be rejected')
            assert registry.values==before
assert autostart.current()==original,'Real startup record must remain unchanged'

calls=[]
class Client:
    def __init__(self):calls.append('start')
    def read(self):calls.append('read');return {}
    def close(self):calls.append('close')
class Windows:
    @staticmethod
    def IsWindow(handle):return handle==123
class Stop:
    def __init__(self):self.stopped=False;self.waits=0
    def is_set(self):return self.stopped
    def wait(self,seconds):
        self.waits+=1
        if self.waits==1:assert not calls,'No backend before Codex appears'
        ui.host=123
class Refresh:
    def __init__(self):self.waits=0
    def clear(self):pass
    def wait(self,seconds):
        self.waits+=1
        if self.waits==1:ui.host=None
        else:ui.stop_event.stopped=True
ui=object.__new__(widget.Widget)
ui.host=None;ui.client=None;ui.events=queue.Queue();ui.stop_event=Stop();ui.refresh_event=Refresh()
with patch.object(widget,'u',Windows),patch.object(widget,'QuotaClient',Client):ui.worker()
assert calls==['start','read','close','start','read','close'],calls
report={'startupBackupAndRestore':'passed','preserveExternalChanges':'passed','frozenAndSourcePaths':'passed','longPathRejected':'passed','codexAbsentAndReopened':'passed','realStartupRecordChanged':False}
(ROOT/'build'/'autostart-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PASS: startup enable/restore, protected changes, EXE paths, absent/reopened Codex; real startup unchanged')
