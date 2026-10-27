import sys
from PIL import Image
# sheet.py OUT.jpg a.jpg b.jpg ... (2 columns, 700x450 tiles)
out, ims = sys.argv[1], [Image.open(p).convert("RGB") for p in sys.argv[2:]]
W, H = 700, 450
rows = (len(ims) + 1) // 2
c = Image.new("RGB", (W * 2, H * rows), "white")
for i, im in enumerate(ims):
    c.paste(im.resize((W, H)), ((i % 2) * W, (i // 2) * H))
c.save(out, quality=80)
