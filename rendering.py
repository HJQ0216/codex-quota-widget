"""4 倍超采样与 Windows 逐像素透明；只向组件自己的窗口绘制。"""
import ctypes as C
from ctypes import wintypes as W
from functools import lru_cache
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'lib'))
from PIL import Image, ImageDraw, ImageFont

SIZE = (44, 108)
SUPERSAMPLE = 4

@lru_cache(maxsize=16)
def font(size, chinese=False):
    name = 'msyh.ttc' if chinese else 'segoeui.ttf'
    return ImageFont.truetype(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name), size)


def render_image(values, scale=1, dark=False, stale=False):
    """先绘制 RGBA 大图，再用 Lanczos 缩小；保留边缘的部分透明度。"""
    width, height = (round(v*scale) for v in SIZE)
    q = scale*SUPERSAMPLE
    image = Image.new('RGBA', (width*SUPERSAMPLE, height*SUPERSAMPLE))
    draw = ImageDraw.Draw(image)
    foreground, track, progress, muted = (('#e4e4e4','#4b4b4b','#cdcdcd','#a0a0a0')
        if dark else ('#353535','#d2d2d2','#636363','#737373'))
    text_boxes = []
    def text(value, cx, cy, color, chinese=False):
        face = font(round(9*q), chinese)
        left, top, right, bottom = draw.textbbox((0,0), value, font=face)
        x, y = cx*q-(left+right)/2, cy*q-(top+bottom)/2
        draw.text((x,y), value, font=face, fill=color)
        text_boxes.append(tuple(v/SUPERSAMPLE for v in (x+left,y+top,x+right,y+bottom)))
    for index, (label, value) in enumerate(zip(('5h','周'),values)):
        cx, cy = 22, 20+54*index
        bounds = tuple(v*q for v in (cx-16,cy-16,cx+16,cy+16))
        line_width = round(2*q)
        draw.ellipse(bounds, outline=track, width=line_width)
        color = '#a77942' if stale else progress
        if value is not None and value > 0:
            if not stale and value <= 10:
                color = '#ba6862'
            elif not stale and value <= 20:
                color = '#b28a41'
            if value >= 100:
                draw.ellipse(bounds, outline=color, width=line_width)
            else:
                end = -90+360*value/100
                draw.arc(bounds,start=-90,end=end,fill=color,width=line_width)
                # 端点与圆环一样保留半透明边缘，避免断口出现方形台阶。
                for angle in (-90,end):
                    radians = math.radians(angle)
                    x,y = (cx+15*math.cos(radians))*q,(cy+15*math.sin(radians))*q
                    radius = line_width/2
                    draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
        text('—' if value is None else f'{value:.0f}%',cx,cy,muted if stale else foreground)
        text(label,cx,cy+24,muted,chinese=index==1)
    result = image.resize((width,height),Image.Resampling.LANCZOS)
    result.info['text_boxes'] = text_boxes
    return result


class BitmapInfo(C.Structure):
    _fields_ = [('size',W.DWORD),('width',W.LONG),('height',W.LONG),
        ('planes',W.WORD),('bitCount',W.WORD),('compression',W.DWORD),
        ('imageSize',W.DWORD),('xPelsPerMeter',W.LONG),('yPelsPerMeter',W.LONG),
        ('clrUsed',W.DWORD),('clrImportant',W.DWORD),('color',W.DWORD)]

class Blend(C.Structure):
    _fields_ = [('operation',W.BYTE),('flags',W.BYTE),('constantAlpha',W.BYTE),('alphaFormat',W.BYTE)]

u = C.WinDLL('user32',use_last_error=True)
g = C.WinDLL('gdi32',use_last_error=True)
u.GetWindowLongW.argtypes = [W.HWND,C.c_int]
u.SetWindowLongW.argtypes = [W.HWND,C.c_int,C.c_long]
u.UpdateLayeredWindow.argtypes = [W.HWND,W.HDC,C.POINTER(W.POINT),C.POINTER(W.SIZE),
    W.HDC,C.POINTER(W.POINT),W.DWORD,C.POINTER(Blend),W.DWORD]
g.CreateCompatibleDC.argtypes = [W.HDC]
g.CreateCompatibleDC.restype = W.HDC
g.CreateDIBSection.argtypes = [W.HDC,C.POINTER(BitmapInfo),W.UINT,C.POINTER(C.c_void_p),W.HANDLE,W.DWORD]
g.CreateDIBSection.restype = W.HBITMAP
g.SelectObject.argtypes = [W.HDC,W.HANDLE]
g.SelectObject.restype = W.HANDLE
g.DeleteObject.argtypes = [W.HANDLE]
g.DeleteDC.argtypes = [W.HDC]


def present_image(hwnd,image):
    """ULW_ALPHA 使用预乘 BGRA；不经过 Tk 色键透明，避免暗色边缘。"""
    width,height = image.size
    raw = image.convert('RGBa').tobytes('raw','BGRa')
    info = BitmapInfo()
    info.size=40;info.width=width;info.height=-height
    info.planes=1;info.bitCount=32;info.imageSize=len(raw)
    bits=C.c_void_p()
    dc=g.CreateCompatibleDC(None)
    bitmap=g.CreateDIBSection(dc,C.byref(info),0,C.byref(bits),None,0)
    if not dc or not bitmap:
        if dc:g.DeleteDC(dc)
        raise C.WinError(C.get_last_error())
    previous=g.SelectObject(dc,bitmap)
    try:
        C.memmove(bits,raw,len(raw))
        style=u.GetWindowLongW(hwnd,-20)
        u.SetWindowLongW(hwnd,-20,style | 0x80000)
        size,origin,blend=W.SIZE(width,height),W.POINT(0,0),Blend(0,0,255,1)
        ok=u.UpdateLayeredWindow(hwnd,None,None,C.byref(size),dc,C.byref(origin),0,C.byref(blend),2)
        if not ok:
            # Tk 若重建过窗口的透明属性，先清除旧色键状态再重试。
            u.SetWindowLongW(hwnd,-20,style & ~0x80000)
            u.SetWindowLongW(hwnd,-20,style | 0x80000)
            if not u.UpdateLayeredWindow(hwnd,None,None,C.byref(size),dc,C.byref(origin),0,C.byref(blend),2):
                raise C.WinError(C.get_last_error())
    finally:
        g.SelectObject(dc,previous)
        g.DeleteObject(bitmap)
        g.DeleteDC(dc)
