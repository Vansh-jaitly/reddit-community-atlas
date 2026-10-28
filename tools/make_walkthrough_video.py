"""
Silent, captioned walkthrough video of the Atlas, built from tools/capture_screens.py screenshots.
Captions are generated from the Atlas artifacts. This complements, and does not replace, a narrated
live demo recorded by the team.

Usage:  python tools/capture_screens.py && python tools/make_walkthrough_video.py
Needs ffmpeg on PATH. Writes docs/demo/atlas_walkthrough.mp4
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs/screenshots"
OUT = ROOT / "docs/demo/atlas_walkthrough.mp4"

meta = json.loads((ROOT / "atlas/web/data/meta.json").read_text())
st = {s["id"]: s for s in json.loads((ROOT / "atlas/web/data/stories.json").read_text())["stories"]}
S = meta["summary"]
clean = sum(int(r["rows_clean"]) for r in meta["cleaning_report"])
A, B, C, D = (st[k]["metrics"] for k in ("popularity", "neighbours", "connectors", "crowds"))
cp = next(iter(D["crypto_pair_affinity"].values()))
mv = next(iter(D["marvel_pair_affinity"].values()))
lead = B["top_links"][0]

SCENES = [
    ("01_discover", 8, f"The Community Atlas: {clean / 1e6:.1f}M Reddit comments, {S['subreddits']} subreddits, {len(S['months'])} months. What really connects these communities?"),
    ("02_atlas_raw", 8, f"Raw overlap: {100 * S['cosine_density']['all']:.2f}% of subreddit pairs share at least one commenter. The map is a hairball dominated by size."),
    ("03_atlas_adjusted", 9, f"Adjusted: only pairs that share far more commenters than size and activity predict ({100 * S['validated_density']['all']:.1f}%). {S['anchor']['communities']} communities appear."),
    ("04_atlas_selected", 9, f"Select r/{A['example']}: its strongest surprising overlaps, with shared vs expected commenters for each."),
    ("06_story_popularity_example", 9, f"Story 1: hubs make up {100 * A['hub_share_cosine']:.0f}% of a topical subreddit's closest neighbours by raw overlap, {100 * A['hub_share_affinity']:.0f}% after adjustment."),
    ("07_story_neighbours", 9, f"Story 2: r/{lead['a']} and r/{lead['b']} share {lead['shared_all']:,} commenters where {lead['expected_all']:,.0f} were expected."),
    ("08_story_connectors", 8, f"Story 3: connectors such as r/{C['connectors'][0]['name']} and r/{C['connectors'][1]['name']} link many communities; giant hubs do not."),
    ("09_story_crowds_timeline", 9, "Story 4: crypto commenters peak with Bitcoin's price in Dec 2017, then fall steeply while Reddit grows."),
    ("10_story_crowds_peak", 7, f"At the peak, r/Bitcoin–r/CryptoCurrency affinity is {cp[S['months'].index(D['baseline_month'])]}×..."),
    ("11_story_crowds_after", 8, f"...and {cp[-1]}× by Sep 2018: the crowd left, and the remaining audience overlaps far more."),
    ("12_story_marvel", 8, f"The Infinity War crowd did the opposite: Marvel affinity fell to {mv[S['months'].index('2018-04')]}× in April 2018. Association, not causation."),
    ("13_explore_profile", 8, "Explore any subreddit: surprising vs raw neighbours, weekly activity and monthly relationship trends."),
    ("14_compare_pair", 8, "Compare two communities across months and quarters, with significance marked."),
    ("15_compare_periods", 8, "Compare two periods: links that appeared (blue) and disappeared (orange), against normal month-to-month churn."),
    ("16_methods", 9, "Methods & data: scope, cleaning, the BiCM null model, validation against the reference code, limitations and downloads."),
]


def font(size):
    for f in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def frame(src: Path, caption: str, dest: Path):
    im = Image.open(src).convert("RGB").resize((1440, 900))
    band = 120
    out = Image.new("RGB", (1440, 900 + band), (17, 17, 16))
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    f = font(28)
    words, lines, cur = caption.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=f) > 1360:
            lines.append(cur); cur = w
        else:
            cur = trial
    lines.append(cur)
    y = 900 + (band - 38 * len(lines)) // 2
    for ln in lines:
        d.text((40, y), ln, font=f, fill=(240, 239, 236)); y += 38
    out.save(dest)


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH")
    tmp = Path(tempfile.mkdtemp(prefix="atlas-video-"))
    listing = []
    for k, (name, secs, cap) in enumerate(SCENES):
        p = tmp / f"{k:02d}.png"
        frame(SHOTS / f"{name}.png", cap, p)
        listing += [f"file '{p.as_posix()}'", f"duration {secs}"]
    listing.append(f"file '{(tmp / f'{len(SCENES) - 1:02d}.png').as_posix()}'")
    (tmp / "list.txt").write_text("\n".join(listing))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                    "-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-crf", "22", str(OUT)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {OUT} ({sum(s for _, s, _ in SCENES)} s)")


if __name__ == "__main__":
    main()
