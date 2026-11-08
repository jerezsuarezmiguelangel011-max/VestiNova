"""Ilustraciones originales de prendas masculinas para demostrar el vestidor.

No son fotografías de mercancía; la API y el móvil las identifican como demo.
Pillow ya forma parte de las dependencias bloqueadas del proyecto.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


def draw_garment(name, color, shirt=False):
    image=Image.new('RGBA',(800,1000))
    mask=Image.new('L',image.size)
    d=ImageDraw.Draw(mask)
    d.polygon([(280,60),(200,100),(25,255),(120,395),(205,320),(190,935),(610,935),(595,320),(680,395),(775,255),(600,100),(520,60)],fill=255)
    d.ellipse((325,10,475,125),fill=0)
    fabric=Image.new('RGBA',image.size)
    pixels=fabric.load()
    for y in range(1000):
        for x in range(800):
            light=1.04-.14*abs(x-400)/400+.025*((y%18)/18)
            pixels[x,y]=tuple(min(255,int(c*light)) for c in color)+(255,)
    image.paste(fabric,(0,0),mask)
    d=ImageDraw.Draw(image)
    seam=tuple(max(0,c-28) for c in color)+(190,)
    d.line([(205,320),(210,915),(590,915),(595,320)],fill=seam,width=3)
    d.line([(37,260),(123,382)],fill=seam,width=4)
    d.line([(677,382),(763,260)],fill=seam,width=4)
    d.arc((316,4,484,138),0,180,fill=seam,width=9)
    d.line([(230,120),(310,80)],fill=seam,width=3)
    d.line([(490,80),(570,120)],fill=seam,width=3)
    if shirt:
        collar=tuple(min(255,c+15) for c in color)+(255,)
        d.polygon([(320,55),(395,118),(350,210),(285,100)],fill=collar,outline=seam,width=3)
        d.polygon([(480,55),(405,118),(450,210),(515,100)],fill=collar,outline=seam,width=3)
        d.rectangle((388,120,412,932),fill=collar,outline=seam,width=2)
        for y in range(220,900,110):
            d.ellipse((397,y,405,y+8),fill=(235,235,229,255),outline=seam)
        d.line([(465,290),(552,290),(552,388),(509,410),(465,388),(465,290)],fill=seam,width=3)
    else:
        d.arc((326,10,474,124),0,180,fill=tuple(max(0,c-48) for c in color)+(255,),width=12)
    target=Path(__file__).resolve().parents[1]/'app/vestidor_virtual/assets'/name
    target.parent.mkdir(exist_ok=True)
    image.save(target,optimize=True)


def main():
    for name,color,shirt in [('polera-gris.png',(112,119,119),False),('polera-azul.png',(47,74,101),False),
                             ('camisa-azul.png',(129,165,185),True),('camisa-blanca.png',(224,224,213),True)]:
        draw_garment(name,color,shirt)
    print('Cuatro ilustraciones PNG transparentes de demostración creadas.')


if __name__=='__main__':
    main()
