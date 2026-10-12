import json
import urllib.request
import numpy as np
from PIL import Image, ImageDraw

def render_map():
    url_map = "http://100.90.252.15:8080/api/map_full"
    url_telem = "http://100.90.252.15:8080/api/telemetry"

    with urllib.request.urlopen(url_map, timeout=3) as resp:
        mdata = json.loads(resp.read().decode('utf-8'))
    
    with urllib.request.urlopen(url_telem, timeout=3) as resp:
        tdata = json.loads(resp.read().decode('utf-8'))

    w = mdata.get("w", 0)
    h = mdata.get("h", 0)
    data = mdata.get("data", [])
    if w <= 0 or h <= 0 or not data:
        print("No map data available")
        return

    arr = np.array(data, dtype=np.int8).reshape((h, w))
    # Flip vertically because ROS OccupancyGrid (0,0) is bottom-left
    arr = np.flipud(arr)

    # Color map: -1 (unknown) -> dark slate (#1e293b), 0 (free) -> dark (#0f172a), 100 (wall) -> bright cyan (#38bdf8)
    img_rgb = np.zeros((h, w, 3), dtype=np.uint8)
    img_rgb[arr == -1] = [30, 41, 59]      # Unknown: dark gray/slate
    img_rgb[arr == 0]  = [15, 23, 42]      # Free space: dark background
    img_rgb[arr > 50]  = [56, 189, 248]    # Walls: bright cyan

    # Scale up for high resolution viewing
    scale = 4
    img = Image.fromarray(img_rgb)
    img = img.resize((w * scale, h * scale), resample=Image.NEAREST)
    draw = ImageDraw.Draw(img)

    # Draw trajectory if available
    ox = mdata.get("ox", 0.0)
    oy = mdata.get("oy", 0.0)
    res = mdata.get("res", 0.05)

    path = tdata.get("trajectory", {}).get("path", [])
    if len(path) > 1:
        pts = []
        for pt in path:
            px = int((pt[0] - ox) / res * scale)
            py = int((h - 1 - (pt[1] - oy) / res) * scale)
            pts.append((px, py))
        draw.line(pts, fill=(234, 179, 8), width=3) # Yellow trail

    # Draw Robot position
    rx = tdata.get("robot", {}).get("x", 0.0)
    ry = tdata.get("robot", {}).get("y", 0.0)
    r_px = int((rx - ox) / res * scale)
    r_py = int((h - 1 - (ry - oy) / res) * scale)
    draw.ellipse([r_px - 8, r_py - 8, r_px + 8, r_py + 8], fill=(239, 68, 68), outline=(255, 255, 255), width=2)

    save_path = "d:/HoMinhKhang/PROJECT/GITHUB_PROJECT/CODE XE TU HANH/scratch/live_slam_map.png"
    img.save(save_path)
    print(f"Map rendered successfully: {w}x{h} ({img.size[0]}x{img.size[1]}px) -> {save_path}")

if __name__ == "__main__":
    render_map()
