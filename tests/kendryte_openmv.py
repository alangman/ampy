import gc
import platform
import uos
import os
import machine
import common
import sensor
import image
import urandom

#lcd init
print("[LCD] init")
st=machine.nt35310()
st.init()
#ov init
print("[CAM] init")
ov=machine.ov5640()
ov.init()
#ov.lcdshow()

# for led
print("[LED] init")
led=machine.led()
led.init()
led.left_on()
led.right_on()

print("[RGB] init")
tripleled=machine.ws2812()
tripleled.init()
tripleled.green()

img = sensor.snapshot()
for i in range(10):
        x = (urandom.getrandbits(30) % (img.width())) - (img.width()//2)
        y = (urandom.getrandbits(30) % (img.height())) - (img.height()//2)
        w = (urandom.getrandbits(30) % (img.width()//2))
        h = (urandom.getrandbits(30) % (img.height()//2))
        r = (urandom.getrandbits(30) % 127) + 128
        g = (urandom.getrandbits(30) % 127) + 128
        b = (urandom.getrandbits(30) % 127) + 128
        img.draw_rectangle(x, y, w, h, color = (r, g, b), thickness = 2, fill = False)
img.show()


