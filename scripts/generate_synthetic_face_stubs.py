"""
Generate lightweight synthetic face stubs for offline testing and CI.
Replaces third-party copyrighted character crops with clean, project-owned placeholders.
"""

from pathlib import Path
from PIL import Image, ImageDraw


def generate_face_stubs() -> None:
    faces_dir = Path("assets/faces")
    faces_dir.mkdir(parents=True, exist_ok=True)

    emotions = ["neutral", "happy", "angry", "sad", "surprised"]
    mouths = ["closed", "open"]

    # Theme colors for emotions
    palette = {
        "neutral": (56, 189, 248, 255),   # Sky blue
        "happy": (74, 222, 128, 255),     # Emerald green
        "angry": (248, 113, 113, 255),    # Coral red
        "sad": (148, 163, 184, 255),      # Slate gray
        "surprised": (251, 191, 36, 255), # Amber gold
    }

    for emotion in emotions:
        color = palette.get(emotion, (100, 116, 139, 255))
        for mouth in mouths:
            out_path = faces_dir / f"{emotion}_{mouth}.png"
            img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Draw avatar circle
            draw.ellipse([(14, 14), (114, 114)], fill=(15, 23, 42, 230), outline=color, width=3)

            # Draw stylized eyes
            if emotion == "happy":
                draw.arc([(34, 40), (54, 56)], start=180, end=360, fill=color, width=2)
                draw.arc([(74, 40), (94, 56)], start=180, end=360, fill=color, width=2)
            elif emotion == "sad":
                draw.arc([(34, 46), (54, 62)], start=0, end=180, fill=color, width=2)
                draw.arc([(74, 46), (94, 62)], start=0, end=180, fill=color, width=2)
            else:
                draw.ellipse([(38, 44), (50, 56)], fill=color)
                draw.ellipse([(78, 44), (90, 56)], fill=color)

            # Draw stylized mouth
            if mouth == "open":
                draw.ellipse([(52, 74), (76, 94)], fill=color)
            else:
                draw.line([(52, 84), (76, 84)], fill=color, width=3)

            img.save(out_path)
            print(f"Generated synthetic face stub: {out_path}")


if __name__ == "__main__":
    generate_face_stubs()
