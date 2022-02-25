# import re

with open("./d2l/zero.file", "rb") as f:
    while content:=f.read(1024):
        content = content.decode().replace("\x00", "", -1)
        if content != "":
            print(content)