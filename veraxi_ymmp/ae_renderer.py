import json
from pathlib import Path
from .ir import TimelineIR

class AfterEffectsRenderer:
    def __init__(self, timeline_ir: TimelineIR):
        self.ir = timeline_ir
        
    def render(self, output_jsx_path: Path):
        fps = self.ir.fps
        
        script = []
        script.append("// Auto-generated Advanced After Effects Script for Zundamon")
        script.append("app.beginUndoGroup('Auto Zundamon Pro Build');")
        script.append("var fps = " + str(fps) + ";")
        
        # 1. Create Main Comp
        script.append("var mainComp = app.project.items.addComp('Zundamon_Final', 1920, 1080, 1, 60, fps);")
        script.append("mainComp.openInViewer();")
        
        # 2. Import PSD
        psd_path = r"C:\Users\YourUser\Pictures\ずんだもん立ち絵素材V3.2\坂本アヒル_ずんだもん立ち絵V3.2_全部入り版.psd.psd".replace('\\', '/')
        script.append(f"var psdFile = new File('{psd_path}');")
        script.append("var importOptions = new ImportOptions(psdFile);")
        script.append("importOptions.importAs = ImportAsType.COMP;")
        script.append("var psdItem = app.project.importFile(importOptions);")
        
        # 3. Add PSD to Main Comp & Add Sliders
        script.append("var zundaLayer = mainComp.layers.add(psdItem);")
        script.append("zundaLayer.name = 'Zundamon';")
        script.append("zundaLayer.property('Position').setValue([1920 - 450, 1080 - 80]);")
        script.append("zundaLayer.property('Scale').setValue([70, 70]);")
        
        # Add Checkbox for Bounce
        script.append("var isTalkingEffect = zundaLayer.Effects.addProperty('ADBE Checkbox Control');")
        script.append("isTalkingEffect.name = 'IsTalking';")
        script.append("isTalkingEffect.property('Checkbox').setValue(0);")
        
        # Add Slider for Lip Sync (0=Closed, 1=Open)
        script.append("var lipSyncEffect = zundaLayer.Effects.addProperty('ADBE Slider Control');")
        script.append("lipSyncEffect.name = 'LipSync';")
        script.append("lipSyncEffect.property('Slider').setValue(0);")
        
        # Bounce Expression
        script.append("""
zundaLayer.property('Position').expression = 
    "var bounce = 0;" +
    "if (effect('IsTalking')('Checkbox') == 1) {" +
    "   bounce = Math.sin(time * 15) * 15;" +
    "}" +
    "value + [0, bounce];";
""")
        
        # 4. Rig the PSD internally
        script.append("""
function rigMouth(comp) {
    for (var i = 1; i <= comp.numLayers; i++) {
        var layer = comp.layer(i);
        if (layer instanceof AVLayer && layer.source instanceof CompItem) {
            rigMouth(layer.source);
        }
        if (layer.name === '*ん' || layer.name === '*お') {
            if (layer.name === '*ん') {
                layer.property('Opacity').expression = "comp('Zundamon_Final').layer('Zundamon').effect('LipSync')('Slider') == 0 ? 100 : 0;";
                layer.enabled = true;
            } else if (layer.name === '*お') {
                layer.property('Opacity').expression = "comp('Zundamon_Final').layer('Zundamon').effect('LipSync')('Slider') == 1 ? 100 : 0;";
                layer.enabled = true;
            }
        }
    }
}
rigMouth(psdItem);
""")
        
        # 5. Global Clips (BG/BGM)
        for gc in self.ir.global_clips:
            file_path = gc.template_item.get('FilePath')
            if not file_path: continue
            
            p = str(Path(file_path).resolve()).replace('\\', '/')
            if p.endswith('.ogg'):
                p = p[:-4] + '.wav'
                
            script.append(f"var itemFile = new File('{p}');")
            script.append("var item = app.project.importFile(new ImportOptions(itemFile));")
            script.append("var layer = mainComp.layers.add(item);")
            
            if 'Volume' in gc.template_item:
                script.append("layer.audioEnabled = true;")
            else:
                script.append("layer.moveToEnd();")
                
        # 6. Dynamic B-Roll
        for img_clip in self.ir.dynamic_image_clips:
            ip = str(img_clip.image_path.resolve()).replace('\\', '/')
            script.append(f"var imgFile = new File('{ip}');")
            script.append("var imgItem = app.project.importFile(new ImportOptions(imgFile));")
            script.append("var layer = mainComp.layers.add(imgItem);")
            script.append(f"layer.inPoint = {img_clip.start_frame / fps};")
            script.append(f"layer.outPoint = {(img_clip.start_frame + img_clip.length) / fps};")
            script.append("layer.property('Position').setValue([1920/2, 1080/2 - 150]);")
            
        # 7. Voices, Text Bubbles, and Keyframes
        script.append("var sliderProp = zundaLayer.effect('LipSync')('Slider');")
        script.append("var talkingProp = zundaLayer.effect('IsTalking')('Checkbox');")
        
        for vc in self.ir.voice_clips:
            start_time = vc.start_frame / fps
            end_time = (vc.start_frame + vc.length) / fps
            
            # Audio
            if vc.audio_path:
                ap = str(vc.audio_path.resolve()).replace('\\', '/')
                script.append(f"var vFile = new File('{ap}');")
                script.append("var vItem = app.project.importFile(new ImportOptions(vFile));")
                script.append("var vLayer = mainComp.layers.add(vItem);")
                script.append(f"vLayer.startTime = {start_time};")
                
            # Speech Bubble Text
            # Create Text Layer
            script.append("var textLayer = mainComp.layers.addText('" + vc.text + "');")
            script.append(f"textLayer.inPoint = {start_time};")
            script.append(f"textLayer.outPoint = {end_time};")
            script.append("textLayer.property('Position').setValue([1920/2, 1080 - 100]);")
            
            script.append("""
var textDoc = textLayer.property("Source Text").value;
textDoc.fontSize = 60;
textDoc.fillColor = [0, 0, 0];
textDoc.justification = ParagraphJustification.CENTER_JUSTIFY;
textLayer.property("Source Text").setValue(textDoc);
""")
            
            # Create Bubble Shape Layer behind text
            script.append("""
var shapeLayer = mainComp.layers.addShape();
shapeLayer.name = 'Bubble';
shapeLayer.moveAfter(textLayer);
shapeLayer.inPoint = """ + str(start_time) + """;
shapeLayer.outPoint = """ + str(end_time) + """;

var shapeGroup = shapeLayer.property('Contents').addProperty('ADBE Vector Group');
var rect = shapeGroup.property('Contents').addProperty('ADBE Vector Shape - Rect');
var fill = shapeGroup.property('Contents').addProperty('ADBE Vector Graphic - Fill');
var stroke = shapeGroup.property('Contents').addProperty('ADBE Vector Graphic - Stroke');

fill.property('Color').setValue([1, 1, 1]); // White
fill.property('Opacity').setValue(90);
stroke.property('Color').setValue([0, 0.5, 0]); // Green
stroke.property('Stroke Width').setValue(8);
rect.property('Roundness').setValue(30);

shapeLayer.property('Position').expression = "var src = thisComp.layer('" + textLayer.name + "'); src.transform.position;";
rect.property('Size').expression = "var src = thisComp.layer('" + textLayer.name + "'); var s = src.sourceRectAtTime(); [s.width + 100, s.height + 60];";
rect.property('Position').expression = "var src = thisComp.layer('" + textLayer.name + "'); var s = src.sourceRectAtTime(); [s.left + s.width/2, s.top + s.height/2];";
""")
            
            # Lip Sync Keyframes
            script.append(f"talkingProp.setValueAtTime({start_time}, 1);")
            script.append(f"talkingProp.setValueAtTime({end_time}, 0);")
            
            if vc.audio_query and 'accent_phrases' in vc.audio_query:
                current_t = start_time
                for phrase in vc.audio_query['accent_phrases']:
                    for mora in phrase['moras']:
                        vowel = mora.get('vowel')
                        v_len = mora.get('vowel_length') or 0
                        c_len = mora.get('consonant_length') or 0
                        
                        if c_len > 0:
                            script.append(f"sliderProp.setValueAtTime({current_t}, 0);")
                            current_t += c_len
                        
                        if vowel and v_len > 0:
                            val = 0
                            v_lower = vowel.lower()
                            if v_lower in ['a', 'i', 'u', 'e', 'o']: val = 1
                            script.append(f"sliderProp.setValueAtTime({current_t}, {val});")
                            current_t += v_len
                    
                    pause_mora = phrase.get('pause_mora')
                    if pause_mora:
                        p_v_len = pause_mora.get('vowel_length') or 0
                        if p_v_len > 0:
                            script.append(f"sliderProp.setValueAtTime({current_t}, 0);")
                            current_t += p_v_len
            
            script.append(f"sliderProp.setValueAtTime({current_t}, 0);")

        script.append("app.endUndoGroup();")
        
        output_jsx_path.write_text("\n".join(script), encoding='utf-8')
        return output_jsx_path
