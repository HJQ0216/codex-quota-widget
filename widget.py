"""Codex 额度浮窗：凭据只读、只在内存传递。"""
import ctypes as C
from ctypes import wintypes as W
import datetime as dt
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import winreg
from rendering import render_image, present_image

ROOT = (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
        else Path(__file__).resolve().parent)
RUNTIME = ROOT / 'runtime'
AUTH = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'auth.json'
REFRESH_SECONDS = 60
TRANSPARENT = '#010203'
RING_DIAMETER = 32
WIDGET_SIZE = (44, 108)
u = C.WinDLL('user32', use_last_error=True)
k = C.WinDLL('kernel32', use_last_error=True)
g = C.WinDLL('gdi32', use_last_error=True)
u.GetForegroundWindow.restype = W.HWND
u.GetAncestor.argtypes = [W.HWND, W.UINT]
u.GetAncestor.restype = W.HWND
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
u.IsWindowVisible.argtypes = [W.HWND]
u.IsIconic.argtypes = [W.HWND]
u.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
u.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
u.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
u.GetWindowLongW.argtypes = [W.HWND, C.c_int]
u.SetWindowLongW.argtypes = [W.HWND, C.c_int, C.c_long]
u.SetWindowRgn.argtypes = [W.HWND, W.HRGN, W.BOOL]
g.CreateRoundRectRgn.argtypes = [C.c_int] * 6
g.CreateRoundRectRgn.restype = W.HRGN
k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k.OpenProcess.restype = W.HANDLE
k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
k.CloseHandle.argtypes = [W.HANDLE]
k.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
k.CreateMutexW.restype = W.HANDLE


def remaining(window):
    """缺失数据保持未知；按服务端窗口长度区分 5 小时和周额度。"""
    if not window or not isinstance(window.get('usedPercent'), (int, float)):
        return None
    return max(0, min(100, 100 - window['usedPercent']))


def windows_from_result(result):
    buckets = result.get('rateLimitsByLimitId') or {}
    bucket = buckets.get('codex') if buckets else result.get('rateLimits')
    bucket = bucket or {}
    windows = [bucket.get('primary'), bucket.get('secondary')]
    return [next((w for w in windows if w and w.get('windowDurationMins') == minutes), None)
            for minutes in (300, 10080)]


class QuotaClient:
    """隔离的 app-server；不启动模型请求，不修改桌面客户端。"""
    def __init__(self):
        RUNTIME.mkdir(exist_ok=True)
        (RUNTIME / 'tmp').mkdir(exist_ok=True)
        env = os.environ.copy()
        env.update(CODEX_HOME=str(RUNTIME), TEMP=str(RUNTIME / 'tmp'),
                   TMP=str(RUNTIME / 'tmp'), PYTHONDONTWRITEBYTECODE='1')
        exe = shutil.which('codex.exe')
        if not exe:
            # 桌面客户端缓存的二进制不一定出现在资源管理器的 PATH 中。
            cache = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'OpenAI/Codex/bin'
            candidates = list(cache.glob('*/codex.exe'))
            if candidates:
                exe = str(max(candidates, key=lambda p: p.stat().st_mtime))
        if not exe:
            raise RuntimeError('找不到 Codex 程序')
        self.proc = subprocess.Popen([exe, 'app-server', '--stdio'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', cwd=ROOT, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.messages = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.rpc('initialize', {'clientInfo': {'name': 'codex_quota_widget', 'version': '0.2.0'},
                                   'capabilities': {'experimentalApi': True}})
            self.send({'method': 'initialized'})
        except Exception:
            self.close()
            raise

    def _read(self):
        for line in self.proc.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                pass
        self.messages.put({'disconnected': True})

    def send(self, message):
        self.proc.stdin.write(json.dumps(message) + '\n')
        self.proc.stdin.flush()

    def tokens(self):
        # 不复制 auth.json、不记录令牌，也不在组件中刷新原账号令牌。
        try:
            tokens = json.loads(AUTH.read_text(encoding='utf-8'))['tokens']
            return {'accessToken': tokens['access_token'], 'chatgptAccountId': tokens['account_id']}
        except (OSError, ValueError, KeyError, TypeError):
            raise RuntimeError('请先在 Codex 登录 ChatGPT 账号') from None

    def rpc(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        self.send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                message = self.messages.get(timeout=1)
            except queue.Empty:
                continue
            if message.get('disconnected'):
                raise RuntimeError('额度服务连接中断')
            if message.get('method') == 'account/chatgptAuthTokens/refresh':
                self.send({'id': message['id'], 'result': self.tokens()})
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError('额度查询失败，请检查 Codex 登录或网络')
                return message.get('result') or {}
        raise RuntimeError('额度查询超时')

    def read(self):
        self.rpc('account/login/start', {'type': 'chatgptAuthTokens', **self.tokens()})
        return self.rpc('account/rateLimits/read', {})

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def codex_window():
    """仅匹配 OpenAI Codex 桌面程序，排除同名网页与终端。"""
    found = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    @callback_type
    def visit(hwnd, _):
        if not u.IsWindowVisible(hwnd):
            return True
        title = C.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, title, len(title))
        if title.value not in ('ChatGPT', 'Codex'):
            return True
        pid = W.DWORD()
        u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        handle = k.OpenProcess(0x1000, False, pid.value)
        if handle:
            path, size = C.create_unicode_buffer(2048), W.DWORD(2048)
            if k.QueryFullProcessImageNameW(handle, 0, path, C.byref(size)):
                name = path.value.lower()
                if 'openai.codex' in name and name.endswith(('chatgpt.exe', 'codex.exe')):
                    found.append(hwnd)
            k.CloseHandle(handle)
        return True
    u.EnumWindows(visit, 0)
    foreground = u.GetForegroundWindow()
    return foreground if foreground in found else (found[0] if found else None)


class Widget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title('Codex Quota Widget')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        # 单位为逻辑像素；窗口跟随时按所在显示器 DPI 缩放。
        self.scale = 1.0
        self.size = WIDGET_SIZE
        self.dark = False
        self.root.configure(bg=TRANSPARENT)
        self.frame = None
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg=TRANSPARENT)
        self.canvas.pack(fill='both', expand=True)
        self.root.update_idletasks()
        self.hwnd = u.GetAncestor(self.root.winfo_id(), 2)
        style = u.GetWindowLongW(self.hwnd, -20)
        u.SetWindowLongW(self.hwnd, -20, style | 0x08000000 | 0x80)
        self.events = queue.Queue()
        self.refresh_event = threading.Event()
        self.stop_event = threading.Event()
        self.windows = [None, None]
        self.updated = 0
        self.error = ''
        self.busy = True
        self.client = None
        self.closing = False
        self.visible = False
        self.last_geometry = None
        self.reported_geometry = False
        self.tooltip = None
        self.host = None
        self.next_discovery = 0
        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label='立即刷新', command=self.refresh)
        self.menu.add_separator()
        self.menu.add_command(label='退出额度浮窗', command=self.close)
        self.canvas.bind('<Button-3>', self.popup)
        self.canvas.bind('<Button-1>', lambda e: self.refresh())
        self.canvas.bind('<Enter>', self.show_tip)
        self.canvas.bind('<Leave>', self.hide_tip)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        threading.Thread(target=self.worker, daemon=True).start()
        self.tick()

    def worker(self):
        client = None
        try:
            while not self.stop_event.is_set():
                # 后台等候 Codex；它未打开时不读取凭据或查询额度。
                if not self.host or not u.IsWindow(self.host):
                    if client:
                        client.close()
                        client = None
                        self.client = None
                    self.stop_event.wait(2)
                    continue
                self.refresh_event.clear()
                self.events.put(('busy', None))
                try:
                    if client is None:
                        client = QuotaClient()
                        self.client = client
                    result = client.read()
                    self.events.put(('data', (windows_from_result(result), time.time())))
                except Exception as error:
                    self.events.put(('error', str(error) if isinstance(error, RuntimeError) else '额度服务暂时不可用'))
                    if client:
                        client.close()
                    client = None
                self.refresh_event.wait(REFRESH_SECONDS)
        finally:
            if client:
                client.close()

    def refresh(self):
        if not self.busy:
            self.refresh_event.set()

    def draw(self):
        stale = bool(self.error or (self.updated and time.time()-self.updated > 125))
        self.frame = render_image([remaining(w) for w in self.windows],self.scale,self.dark,stale)
        self.canvas.configure(width=self.frame.width,height=self.frame.height)
        self.root.update_idletasks()
        if self.root.state() != 'withdrawn':
            self.hwnd = u.GetAncestor(self.root.winfo_id(),2)
            present_image(self.hwnd,self.frame)
            (ROOT/'render-state.json').write_text(json.dumps({
                'renderer':'4x Lanczos + per-pixel alpha','size':self.frame.size,
                'scale':self.scale,'alphaBlendSucceeded':True,'renderedAt':time.time()
            },indent=2),encoding='utf-8')

    def update_palette(self, host):
        dark = W.BOOL()
        try:
            dwm = C.WinDLL('dwmapi')
            dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]
            known = dwm.DwmGetWindowAttribute(host, 20, C.byref(dark), C.sizeof(dark)) == 0
        except OSError:
            known = False
        if not known:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                    dark.value = not winreg.QueryValueEx(key, 'AppsUseLightTheme')[0]
            except OSError:
                dark.value = False
        if bool(dark.value) != self.dark:
            self.dark = bool(dark.value)
            self.draw()

    def follow(self):
        now = time.monotonic()
        if now >= self.next_discovery or not self.host or not u.IsWindow(self.host):
            self.host = codex_window()
            self.next_discovery = now + 2
        host = self.host
        self.hwnd = u.GetAncestor(self.root.winfo_id(), 2)
        foreground = u.GetForegroundWindow()
        foreground_pid = W.DWORD()
        u.GetWindowThreadProcessId(foreground, C.byref(foreground_pid))
        show = bool(host and u.IsWindowVisible(host) and not u.IsIconic(host)
                    and (foreground == host or foreground_pid.value == os.getpid() or self.menu.winfo_ismapped()))
        if show:
            rect, origin = W.RECT(), W.POINT(0,0)
            u.GetClientRect(host,C.byref(rect))
            u.ClientToScreen(host,C.byref(origin))
            dpi = u.GetDpiForWindow(host) if hasattr(u,'GetDpiForWindow') else 96
            scale = dpi/96
            width,height = round(self.size[0]*scale),round(self.size[1]*scale)
            # 底边留出头像行；不覆盖左下角头像和账户按钮。
            x,y = origin.x+round(6*scale),origin.y+rect.bottom-round((self.size[1]+64)*scale)
            show = rect.right > round(460*scale) and rect.bottom > round(330*scale)
            self.update_palette(host)
            geometry = (x,y,width,height)
            if show and (geometry != self.last_geometry or not self.visible):
                self.scale=scale
                self.root.geometry(f'{width}x{height}{x:+}{y:+}')
                u.SetWindowRgn(self.hwnd, None, True)
                self.root.deiconify()
                self.hwnd = u.GetAncestor(self.root.winfo_id(), 2)
                style = u.GetWindowLongW(self.hwnd, -20)
                u.SetWindowLongW(self.hwnd, -20, style | 0x08000080)
                u.SetWindowPos(self.hwnd,W.HWND(-1),x,y,width,height,0x0010|0x0040)
                self.last_geometry=geometry
                self.draw()
        if not show and self.visible:
            self.root.withdraw()
            self.hide_tip()
        if show != self.visible or getattr(self,'reported_geometry',None) != self.last_geometry:
            (ROOT/'window-state.json').write_text(json.dumps({'visible':show,'hostFound':bool(host),'foregroundIsCodex':foreground==host,'geometry':self.last_geometry,'scale':self.scale,'checkedAt':time.time()},indent=2),encoding='utf-8')
            self.reported_geometry=self.last_geometry
        self.visible=show

    def show_tip(self, _=None):
        self.hide_tip()
        self.tooltip=tk.Toplevel(self.root)
        self.tooltip.withdraw()
        self.tooltip.overrideredirect(True)
        self.tooltip.attributes('-topmost',True)
        rows=[]
        for name,window in zip(('5 小时','每周'),self.windows):
            reset=(window or {}).get('resetsAt')
            rows.append(name+'重置：'+(dt.datetime.fromtimestamp(reset).strftime('%m月%d日 %H:%M') if reset else '未知'))
        if self.busy:
            rows.append('正在同步额度…')
        rows.append('同步：'+(dt.datetime.fromtimestamp(self.updated).strftime('%H:%M:%S') if self.updated else '尚未取得数据'))
        if self.error:
            rows.append(self.error)
        tk.Label(self.tooltip,text='\n'.join(rows),justify='left',bg='#30322f',fg='#f4f4ef',
                 font=('Microsoft YaHei UI',9),padx=12,pady=9).pack()
        x=self.root.winfo_x()+round((self.size[0]+10)*self.scale)
        self.tooltip.geometry(f'{x:+}{self.root.winfo_y():+}')
        self.tooltip.update_idletasks()
        tip_hwnd=u.GetAncestor(self.tooltip.winfo_id(),2)
        tip_style=u.GetWindowLongW(tip_hwnd,-20)
        u.SetWindowLongW(tip_hwnd,-20,tip_style | 0x08000080)
        self.tooltip.deiconify()

    def hide_tip(self, _=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip=None

    def popup(self,event):
        self.hide_tip()
        try:
            self.menu.tk_popup(event.x_root,event.y_root)
        finally:
            self.menu.grab_release()

    def tick(self):
        if self.closing:
            return
        changed=False
        while True:
            try:
                kind,value=self.events.get_nowait()
            except queue.Empty:
                break
            changed=True
            self.busy=kind=='busy'
            if kind=='data':
                self.windows,self.updated=value
                self.error=''
                # 只保存额度和同步状态，不保存任何认证字段。
                (ROOT/'status.json').write_text(json.dumps({'windows':self.windows,'updatedAt':self.updated},ensure_ascii=False,indent=2),encoding='utf-8')
            elif kind=='error':
                self.error=value
        if changed:
            self.draw()
        self.follow()
        self.root.after(200,self.tick)

    def close(self):
        self.closing=True
        self.stop_event.set()
        self.refresh_event.set()
        self.root.withdraw()
        self.root.after(3500,self.root.destroy)


def main():
    if sys.argv[1:2] == ['--autostart']:
        from autostart import main as autostart_main
        raise SystemExit(autostart_main(sys.argv[2:]))
    try:
        C.WinDLL('shcore').SetProcessDpiAwareness(2)
    except (OSError,AttributeError):
        u.SetProcessDPIAware()
    mutex=k.CreateMutexW(None,False,'Local\\CodexQuotaWidget')
    if C.get_last_error()==183:
        return
    widget=Widget()
    try:
        widget.root.mainloop()
    finally:
        widget.stop_event.set()
        widget.refresh_event.set()
        if widget.client:
            widget.client.close()
        k.CloseHandle(mutex)


if __name__=='__main__':
    main()
