"""检查抗锯齿、透明混合、字体边界与四档 DPI，不替代桌面截图。"""
import json
from pathlib import Path
import tkinter as tk
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import widget
from rendering import render_image,present_image,Image
root=Path(__file__).resolve().parents[1]
(root/'build').mkdir(exist_ok=True)
assert widget.remaining(None) is None
assert widget.remaining({'usedPercent':0})==100
assert widget.remaining({'usedPercent':100})==0
assert widget.remaining({'usedPercent':110})==0
assert widget.remaining({'usedPercent':-1})==100
checks=[]
for scale in (1,1.25,1.5,2):
 for dark in (False,True):
  for values,stale in (([71,37],False),([100,0],False),([None,None],False),([71,37],True)):
   image=render_image(values,scale,dark,stale)
   assert image.size==(round(44*scale),round(108*scale))
   boxes=image.info['text_boxes']
   for i,box in enumerate(boxes):
    assert box[0]>=0 and box[1]>=0 and box[2]<=image.width and box[3]<=image.height
    for old in boxes[:i]:
     assert not (min(box[2],old[2])>max(box[0],old[0]) and min(box[3],old[3])>max(box[1],old[1]))
   for index,box in enumerate(boxes[::2]):
    assert abs((box[0]+box[2])/2-22*scale)<.5
    assert abs((box[1]+box[3])/2-(20+54*index)*scale)<.5
    assert box[2]-box[0]<=28*scale
   # 真实像素有大量部分透明的边缘，而不是只有透明/不透明两种台阶。
   hist=image.getchannel('A').histogram()
   partial=sum(hist[1:255]);levels=sum(n>0 for n in hist[1:255])
   assert partial>100 and levels>30,(scale,partial,levels)
   assert image.getpixel((0,0))[3]==0
   raw=image.convert('RGBa').tobytes('raw','BGRa')
   assert all(max(raw[i:i+3])<=raw[i+3] for i in range(0,len(raw),4))
   checks.append({'scale':scale,'dark':dark,'stale':stale,'partialAlphaPixels':partial,'alphaLevels':levels,'passed':True})
# 验证 Windows 接收实际的逐像素透明表面；只针对本测试自己创建的隐藏窗口。
ui=tk.Tk();ui.withdraw();ui.update_idletasks()
hwnd=widget.u.GetAncestor(ui.winfo_id(),2)
present_image(hwnd,render_image([71,37],1.25))
ui.destroy()
# 原生分辨率的渲染预览；不代表桌面截图。
preview=Image.new('RGB',(220,170),'#ededed')
for index,dark in enumerate((False,True)):
 bg=Image.new('RGBA',(110,170),'#202020' if dark else '#f4f4f4')
 fg=render_image([71,37],1.25,dark)
 bg.alpha_composite(fg,(27,15))
 preview.paste(bg.convert('RGB'),(110*index,0))
preview.save(root/'build'/'render-preview.png')
(root/'build'/'verification.json').write_text(json.dumps({'renderer':'4x supersampling / Lanczos / premultiplied per-pixel alpha','nativeAlphaPresentation':'passed','layoutAndAlphaChecks':checks,'desktopScreenshot':'unverified; preview is renderer output'},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: 32 DPI/theme/state cases; smooth alpha; centered text; native alpha presentation')
