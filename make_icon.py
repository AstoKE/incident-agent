from PIL import Image

img = Image.open(r"src\incident_agent\ui_qt\assets\app.png").convert("RGBA")
img.save(
    r"src\incident_agent\ui_qt\assets\app.ico",
    sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
)

print("saved app.ico")