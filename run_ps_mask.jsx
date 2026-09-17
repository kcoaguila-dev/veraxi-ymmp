var f = new File("C:/dev/workspace/active/veraxi-ymmp/assets/apple.jpg");
app.open(f);
var doc = app.activeDocument;
doc.activeLayer.isBackgroundLayer = false;
