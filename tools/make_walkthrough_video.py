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

meta = json.loads((ROOT / "atlas/web/data/meta.json").read_text(encoding="utf-8"))
st = {s["id"]: s for s in json.loads((ROOT / "atlas/web/data/stories.json").read_text(encoding="utf-8"))["stories"]}
S = meta["summary"]
clean = sum(int(r["rows_clean"]) for r in meta["cleaning_report"])
A, B, C, D = (st[k]["metrics"] for k in ("popularity", "neighbours", "connectors", "crowds"))
cp = next(iter(D["crypto_pair_affinity"].values()))
mv = next(iter(D["marvel_pair_affinity"].values()))
lead = B["top_links"][0]
anc = S["anchor"]
comm = (f"{anc['communities_major']} major communities (plus {anc['small_groups']} small groups and {anc['isolates']} isolate{'s' if anc['isolates'] != 1 else ''})"
        if "communities_major" in anc else f"{anc['communities']} communities")
rab = D["crypto_cross_rate_ab"]
bi = S["months"].index(D["baseline_month"])
sw = D.get("starwars")

SCENES = [
    ("01_start", 8, f"Two communities share thousands of commenters. Are their audiences unusually connected? {clean / 1e6:.1f}M comments, {S['subreddits']} subreddits, {len(S['months'])} months."),
    ("02_start_raw", 8, f"Link every pair that shares a commenter: {100 * S['cosine_density']['all']:.2f}% of pairs connect. One person active in many places links all of them."),
    ("05_atlas_surprise", 8, "Ask what chance would produce: grey lines share about what size and activity predict; coloured lines share far more."),
    ("03_atlas_adjusted", 9, f"Keep only the surprising: {100 * S['validated_density']['all']:.1f}% of pairs, {comm}."),
    ("04_atlas_selected", 9, f"Open r/{A['example']}: its strongest surprising overlaps, with shared vs expected commenters for each."),
    ("12_story_takeaway", 9, f"Each discovery ends with a takeaway: hubs are {100 * A['hub_share_cosine']:.0f}% of a topical subreddit's closest neighbours by raw overlap, {100 * A['hub_share_affinity']:.0f}% after adjustment."),
    ("07_story_neighbours", 9, f"Discovery 2: r/{lead['a']} and r/{lead['b']} share {lead['shared_all']:,} commenters where {lead['expected_all']:,.0f} were expected; the same test also finds audiences that keep apart."),
    ("08_story_connectors", 8, f"Discovery 3: connectors such as r/{C['connectors'][0]['name']} and r/{C['connectors'][1]['name']} reach many clusters; r/{C['giants']['name']} keeps every surprising link inside its own."),
    ("09_story_crowds_timeline", 9, "Discovery 4: crypto commenters peak with Bitcoin's price in Dec 2017, then fall steeply while Reddit grows."),
    ("10_story_crowds_peak", 7, f"The obvious reading: r/Bitcoin–r/CryptoCurrency affinity goes from {cp[bi]}× at the peak to {cp[-1]}× by Sep 2018..."),
    ("11_story_crowds_after", 9, f"...the careful one: the share of r/Bitcoin commenters also in r/CryptoCurrency moved only {100 * rab[bi]:.0f}% → {100 * rab[-1]:.0f}%. The ratio rose because the expectation shrank with the communities."),
    ("21_story_crowds_starwars", 8, f"A crowd arriving: The Last Jedi took r/StarWars to {sw['dec_over_nov']:.2f}× its November commenters; affinity with its fandom neighbours dipped and recovered." if sw else "A crowd arriving shows the same arithmetic in reverse."),
    ("22_story_crowds_marvel", 8, f"Infinity War doubled r/marvelstudios' weekly commenters; r/marvelstudios–r/Marvel affinity fell to {mv[S['months'].index('2018-04')]}× in April 2018 while cross-posting rose. Association, not causation."),
    ("13_explore_profile", 8, "Explore any subreddit: surprising vs raw neighbours, weekly activity and monthly relationship trends."),
    ("14_compare_pair", 8, "Compare two communities across months and quarters, with significance marked."),
    ("15_compare_periods", 8, "Compare two periods: links that appeared (blue) and disappeared (orange), against normal month-to-month churn."),
    ("16_pipeline_expected", 9, "How it's made: nine stages with real counts, a worked example, the tests that guard each step, and what is precomputed versus computed in the browser."),
    ("18_about", 8, f"Scope & limits: one sample of {S['subreddits']} subreddits, {len(S['months'])} months, comments only. Associations, not causes; co-presence, not conversation."),
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
