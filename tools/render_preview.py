"""使用真实组件渲染器生成效果示意图；不截取桌面或读取真实额度。"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rendering import Image,ImageDraw,ImageFont,font,render_image
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs'/'images'
OUT.mkdir(parents=True,exist_ok=True)
image=Image.new('RGB',(1200,760),'#fafaf9')
d=ImageDraw.Draw(image)
def text(x,y,value,size=18,color='#333333',chinese=False):
 d.text((x,y),value,font=font(size,chinese),fill=color)
text(44,35,'Codex Quota Widget',42)
text(46,96,'5 小时与每周额度，一眼可见',23,'#707070',True)
for index,dark in enumerate((False,True)):
 x,y=40+576*index,175
 surface='#202020' if dark else '#ffffff'
 rail='#272727' if dark else '#f0f0ef'
 side='#242424' if dark else '#f7f7f6'
 ink='#d8d8d8' if dark else '#414141'
 faint='#484848' if dark else '#e5e5e4'
 text(x+4,142,'DARK' if dark else 'LIGHT',14,'#777777')
 d.rounded_rectangle((x,y,x+544,y+474),radius=16,fill=surface)
 d.rounded_rectangle((x,y,x+112,y+474),radius=16,fill=rail)
 d.rectangle((x+96,y+1,x+112,y+473),fill=rail)
 d.rectangle((x+112,y+1,x+291,y+473),fill=side)
 # 用通用图形表示导航，不使用 OpenAI 标志或用户工作内容。
 d.rounded_rectangle((x+29,y+27,x+83,y+61),radius=8,outline=faint,width=2)
 d.line((x+56,y+35,x+56,y+53),fill=ink,width=2)
 d.line((x+47,y+44,x+65,y+44),fill=ink,width=2)
 d.ellipse((x+44,y+92,x+63,y+111),outline=ink,width=2)
 d.line((x+60,y+108,x+69,y+117),fill=ink,width=2)
 text(x+132,y+29,'示例项目',18,ink,True)
 text(x+132,y+82,'README.md',16,ink)
 text(x+132,y+120,'新对话',16,'#999999' if dark else '#8a8a8a',True)
 d.rounded_rectangle((x+311,y+34,x+516,y+42),radius=4,fill=faint)
 d.rounded_rectangle((x+311,y+62,x+485,y+70),radius=4,fill=faint)
 d.rounded_rectangle((x+311,y+90,x+501,y+98),radius=4,fill=faint)
 rgba=image.convert('RGBA')
 ring=render_image([71,37],2,dark)
 rgba.alpha_composite(ring,(x+12,y+130))
 image=rgba.convert('RGB');d=ImageDraw.Draw(image)
 # 与圆环同一中心线的通用头像。
 d.ellipse((x+24,y+392,x+88,y+456),fill='#444444' if dark else '#ddddda')
 face=font(20)
 d.text((x+56,y+424),'U',font=face,anchor='mm',fill=ink)
text(44,681,'示例额度 71% / 37% · 项目真实渲染器 · 非桌面截图',18,'#747474',True)
text(44,716,'Windows overlay  /  32 px rings  /  per-pixel alpha  /  MIT',15,'#909090')
image.save(OUT/'preview.png')
for dark in (False,True):
 render_image([71,37],3,dark).save(OUT/('widget-dark.png' if dark else 'widget-light.png'))
print('Created labeled preview images:',OUT)
