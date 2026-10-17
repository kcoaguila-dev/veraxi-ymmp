import json
from pathlib import Path
import cv2
import numpy as np

def verify_ymmp():
    ymmp_path = Path('projects/02_market_analysis_2026/ymmp/final_video.ymmp')
    with open(ymmp_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    items = data['Timelines'][0]['Items']
    face_items = [it for it in items if 'TachieFaceItem' in it.get('$type', '')]

    print(f"Total TachieFaceItems on timeline: {len(face_items)}")

    zunda_faces = [it for it in face_items if it.get('CharacterName') == 'ずんだもん']
    metan_faces = [it for it in face_items if it.get('CharacterName') == '四国めたん']

    print(f"Zundamon TachieFaceItems: {len(zunda_faces)}")
    print(f"Metan TachieFaceItems: {len(metan_faces)}")

    z_open = sum(1 for it in zunda_faces if 'n108' in it['TachieFaceParameter']['EnableLayers'])
    z_closed = sum(1 for it in zunda_faces if 'n109' in it['TachieFaceParameter']['EnableLayers'])
    print(f"Zundamon: {z_open} OPEN mouth slices (n108), {z_closed} CLOSED mouth slices (n109)")

    m_open = sum(1 for it in metan_faces if 'n48' in it['TachieFaceParameter']['EnableLayers'])
    m_closed = sum(1 for it in metan_faces if 'n47' in it['TachieFaceParameter']['EnableLayers'])
    print(f"Metan: {m_open} OPEN mouth slices (n48), {m_closed} CLOSED mouth slices (n47)")

    print("\nFirst 8 Zundamon slices:")
    for it in zunda_faces[:8]:
        frm = it['Frame']
        lng = it['Length']
        rem = it.get('Remark', '')
        is_op = 'n108' in it['TachieFaceParameter']['EnableLayers']
        status = "OPEN (n108)" if is_op else "CLOSED (n109)"
        print(f"  Frame {frm:4d} - {frm+lng:4d} (len={lng:2d} frames, {lng/30:.2f}s): {status} [{rem}]")

def verify_video():
    video_path = 'projects/02_market_analysis_2026/qa_test.mp4'
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = total_frames / fps
    print(f"\nVideo info: {total_frames} frames, {fps} fps, duration = {dur:.2f}s")

    # In 02_market_analysis_2026:
    # Line 1: Zundamon speaks from t=0 to ~3.8s
    # In line 1:
    # 0.000s - 0.194s: CLOSED (frames 0-5)
    # 0.194s - 0.317s: OPEN (frames 6-9)
    # 0.317s - 0.435s: CLOSED (frames 10-12)
    # 0.435s - 0.621s: OPEN (frames 13-18)
    # 0.621s - 1.055s: CLOSED (comma pause!) (frames 19-31)
    
    # Let's extract frame 3 (CLOSED), frame 8 (OPEN), frame 11 (CLOSED), frame 16 (OPEN), frame 25 (CLOSED - pause)
    sampled_indices = [3, 8, 11, 16, 25]
    frames = {}
    for idx in range(35):
        ret, frame = cap.read()
        if not ret:
            break
        if idx in sampled_indices:
            frames[idx] = frame

    cap.release()

    # Zundamon is on the right side: X around 1180 to 1920.
    # Let's locate mouth region:
    # Height of character is 1250, bottom anchored at 1080 - 1250 + 250 = 80
    # Head of Zundamon is around Y: 100-400, X: 1300-1650
    # Mouth is around Y: 300-380, X: 1420-1520
    
    # Let's measure difference between frame 3 (closed) and frame 8 (open)
    f_closed = frames[3]
    f_open = frames[8]
    diff = cv2.absdiff(f_closed, f_open)
    max_diff = np.max(diff)
    mean_diff = np.mean(diff)
    print(f"\nFrame 3 (CLOSED) vs Frame 8 (OPEN) diff: max={max_diff}, mean={mean_diff:.3f}")
    
    # Also compare frame 8 (OPEN) vs frame 25 (CLOSED pause)
    f_pause = frames[25]
    diff_pause = cv2.absdiff(f_open, f_pause)
    print(f"Frame 8 (OPEN) vs Frame 25 (CLOSED pause) diff: max={np.max(diff_pause)}, mean={np.mean(diff_pause):.3f}")

    # Compare frame 3 (CLOSED) vs frame 25 (CLOSED pause) -> should be nearly identical mouth!
    # Crop mouth region: Y: 280 to 360, X: 1400 to 1540
    mouth_closed_1 = f_closed[280:360, 1400:1540]
    mouth_open = f_open[280:360, 1400:1540]
    mouth_closed_2 = f_pause[280:360, 1400:1540]
    
    mouth_diff_open = np.mean(cv2.absdiff(mouth_closed_1, mouth_open))
    mouth_diff_closed = np.mean(cv2.absdiff(mouth_closed_1, mouth_closed_2))
    print(f"Mouth region diff (Closed vs Open): {mouth_diff_open:.3f}")
    print(f"Mouth region diff (Closed vs Closed-pause): {mouth_diff_closed:.3f}")

    # Save a side-by-side comparison artifact
    side_by_side = np.hstack([mouth_closed_1, mouth_open, mouth_closed_2])
    # Enlarge 4x for clear inspection
    side_by_side = cv2.resize(side_by_side, (0, 0), fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    # Add text labels
    cv2.putText(side_by_side, "CLOSED (0.1s)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(side_by_side, "OPEN (0.25s)", (560 + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(side_by_side, "PAUSE (0.8s)", (1120 + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
    out_dir = Path("artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_img_path = str(out_dir / "mouth_verification.png")
    cv2.imwrite(out_img_path, side_by_side)
    print(f"\nSaved mouth comparison artifact to: {out_img_path}")

if __name__ == '__main__':
    verify_ymmp()
    verify_video()
