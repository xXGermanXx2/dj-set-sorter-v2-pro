from __future__ import annotations
import datetime as dt
import html
import math
from pathlib import Path


def format_duration(seconds: float) -> str:
    s = int(round(seconds or 0))
    if s <= 0:
        return "–"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def generate_svg_curve(tracks: list, width: int = 960, height: int = 180) -> str:
    if not tracks:
        return ""
    n = len(tracks)
    pad_x = 40
    pad_y = 25
    eff_w = width - 2 * pad_x
    eff_h = height - 2 * pad_y

    pts = []
    for i, t in enumerate(tracks):
        x = pad_x + (i / max(1, n - 1)) * eff_w if n > 1 else pad_x + eff_w / 2
        e = getattr(t, "energy", 50.0) or 50.0
        # Energy 0..100 maps to y = height - pad_y .. pad_y
        y = pad_y + eff_h * (1.0 - min(100.0, max(0.0, e)) / 100.0)
        pts.append((x, y, t, e))

    line_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in pts)
    area_d = f"{line_d} L {pts[-1][0]:.1f},{height - pad_y:.1f} L {pts[0][0]:.1f},{height - pad_y:.1f} Z"

    # SVG circles and tooltips
    dots = []
    for i, (x, y, t, e) in enumerate(pts, 1):
        color = "#10b981" if e < 50 else "#f59e0b" if e < 75 else "#ef4444"
        title = html.escape(f"#{i} {getattr(t, 'artist', '')} – {getattr(t, 'title', '')} (Energie: {e:.1f})")
        dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}" stroke="#fff" stroke-width="2">'
            f'<title>{title}</title></circle>'
        )

    # Grid lines (25%, 50%, 75%)
    grid = []
    for pct in (25, 50, 75):
        gy = pad_y + eff_h * (1.0 - pct / 100.0)
        grid.append(f'<line x1="{pad_x}" y1="{gy:.1f}" x2="{width - pad_x}" y2="{gy:.1f}" stroke="#e2e8f0" stroke-dasharray="4,4"/>'
                    f'<text x="{pad_x - 8}" y="{gy + 4:.1f}" font-size="10" fill="#94a3b8" text-anchor="end">{pct}%</text>')

    svg = f"""<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" style="overflow:visible;" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="curveGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#3b82f6" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  {''.join(grid)}
  <path d="{area_d}" fill="url(#curveGrad)" />
  <path d="{line_d}" fill="none" stroke="#2563eb" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  {''.join(dots)}
</svg>"""
    return svg


def write_preview_html(tracks, name: str, output: Path, set_info: dict | None = None) -> None:
    n = len(tracks)
    a = max(1, round(n * .45))
    b = max(a + 1, round(n * .82)) if n > 2 else n

    total_dur_sec = sum(getattr(t, "duration", 0.0) or 210.0 for t in tracks)
    total_dur_str = format_duration(total_dur_sec)

    bpms = [getattr(t, "analyzed_bpm", 0) or getattr(t, "bpm", 0) for t in tracks if (getattr(t, "analyzed_bpm", 0) or getattr(t, "bpm", 0))]
    avg_bpm = f"{sum(bpms) / len(bpms):.1f}" if bpms else "–"
    bpm_range = f"{min(bpms):.1f} – {max(bpms):.1f}" if bpms else "–"

    energies = [getattr(t, "energy", 0.0) for t in tracks]
    avg_energy = f"{sum(energies) / len(energies):.1f}" if energies else "–"

    curve_svg = generate_svg_curve(tracks)

    rows = []
    for i, track in enumerate(tracks, 1):
        # Determine phase
        phase = getattr(track, "phase", "")
        if not phase:
            phase = "Aufbau" if i <= a else "Steigerung" if i <= b else "Peak"
        
        css = "peak" if "Peak" in phase else "rise" if ("Steigerung" in phase or "Drive" in phase) else "build"

        analyzed_bpm = f"{track.analyzed_bpm:.1f}" if getattr(track, "analyzed_bpm", 0) else (f"{track.bpm:.1f}" if getattr(track, "bpm", 0) else "–")
        key = html.escape(str(getattr(track, "musical_key", "") or "–"))
        audio = f"{track.audio_energy:.1f}" if getattr(track, "audio_analyzed", False) else "–"
        waveform = f"{track.waveform_score:.0f}" if getattr(track, "audio_analyzed", False) else "–"
        dur_str = format_duration(getattr(track, "duration", 0.0))
        energy_val = getattr(track, "energy", 0.0)

        rows.append(
            f"<tr class='{css}'>"
            f"<td><strong>{i:02d}</strong></td>"
            f"<td><span class='phase-pill {css}'>{html.escape(phase)}</span></td>"
            f"<td><strong>{html.escape(track.artist or 'Unbekannt')}</strong><br><span class='title-text'>{html.escape(track.title or Path(track.path).stem)}</span></td>"
            f"<td>{dur_str}</td>"
            f"<td><strong>{analyzed_bpm}</strong></td>"
            f"<td><span class='key-pill'>{key}</span></td>"
            f"<td><div class='energy-bar-wrap'><div class='energy-bar' style='width:{min(100, max(5, int(energy_val)))}%'></div><span>{energy_val:.1f}</span></div></td>"
            f"<td>{html.escape(track.genre or '–')}</td>"
            f"<td>{audio}</td>"
            f"<td>{waveform}</td>"
            f"<td class='path' title='{html.escape(track.path)}'>{html.escape(Path(track.path).name)}</td>"
            f"</tr>"
        )

    curve_info_text = ""
    if set_info and "curve_title" in set_info:
        curve_info_text = f"<div class='info-badge'>Dramaturgie: {html.escape(set_info['curve_title'])}</div>"

    document = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DJ Set Vorschau – {html.escape(name)}</title>
<style>
:root {{
  --bg: #0f172a;
  --card: #1e293b;
  --card-border: #334155;
  --text: #f8fafc;
  --muted: #94a3b8;
  --primary: #3b82f6;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }}
main {{ max-width: 1400px; margin: auto; }}
.header {{ background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; padding: 28px; margin-bottom: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }}
.header h1 {{ margin: 0 0 8px; font-size: 28px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 10px; }}
.header .badge {{ font-size: 12px; background: #2563eb; color: #fff; padding: 4px 10px; border-radius: 999px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
.muted {{ color: var(--muted); font-size: 14px; }}
.info-badge {{ display: inline-block; background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); padding: 5px 12px; border-radius: 8px; font-size: 13px; font-weight: 500; margin-top: 10px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 22px 0 0; }}
.card {{ padding: 18px; border-radius: 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--card-border); }}
.card span {{ color: var(--muted); font-size: 13px; font-weight: 500; }}
.card b {{ display: block; font-size: 26px; color: #fff; margin-top: 4px; font-weight: 700; }}

.chart-card {{ background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; padding: 24px; margin-bottom: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); }}
.chart-card h3 {{ margin: 0 0 16px; font-size: 16px; font-weight: 600; color: #e2e8f0; }}

.table-card {{ background: var(--card); border: 1px solid var(--card-border); border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.2); }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th {{ background: #0f172a; color: #94a3b8; font-weight: 600; text-align: left; padding: 14px 12px; position: sticky; top: 0; border-bottom: 1px solid var(--card-border); }}
td {{ padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: middle; }}
tr:hover {{ background: rgba(255,255,255,0.02); }}

.phase-pill {{ display: inline-block; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; }}
.phase-pill.build {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
.phase-pill.rise {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}
.phase-pill.peak {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }}

.key-pill {{ display: inline-block; background: #334155; color: #e2e8f0; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }}
.energy-bar-wrap {{ display: flex; align-items: center; gap: 8px; width: 110px; }}
.energy-bar {{ height: 8px; border-radius: 4px; background: linear-gradient(90deg, #10b981, #f59e0b, #ef4444); }}
.energy-bar-wrap span {{ font-size: 12px; font-weight: 600; color: #e2e8f0; min-width: 30px; }}

.title-text {{ color: #cbd5e1; font-size: 12px; }}
.path {{ font-size: 11px; color: #64748b; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.footer-note {{ margin-top: 20px; padding: 14px 18px; border-radius: 10px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); font-size: 13px; color: #34d399; }}
</style>
</head>
<body>
<main>
  <div class="header">
    <h1>🎧 DJ Set Vorschau: {html.escape(name)} <span class="badge">V2 Pro</span></h1>
    <div class="muted">Erstellt am {dt.datetime.now().strftime('%d.%m.%Y um %H:%M:%S')} · Rekordbox & VirtualDJ kompatibel</div>
    {curve_info_text}
    <div class="cards">
      <div class="card"><span>Gesamtdauer</span><b>{total_dur_str}</b></div>
      <div class="card"><span>Anzahl Tracks</span><b>{n}</b></div>
      <div class="card"><span>Durchschnitts-BPM</span><b>{avg_bpm}</b></div>
      <div class="card"><span>BPM-Spanne</span><b>{bpm_range}</b></div>
      <div class="card"><span>Durchschnitts-Energie</span><b>{avg_energy}</b></div>
    </div>
  </div>

  <div class="chart-card">
    <h3>📊 Energie-Verlauf der Set-Dramaturgie</h3>
    {curve_svg}
  </div>

  <div class="table-card">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Phase</th>
          <th>Interpret / Titel</th>
          <th>Dauer</th>
          <th>BPM</th>
          <th>Key</th>
          <th>Energie</th>
          <th>Genre</th>
          <th>Audio-RMS</th>
          <th>Waveform</th>
          <th>Dateiname</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>

  <div class="footer-note">
    🛡️ <strong>100% Sicher:</strong> Diese Vorschau sowie der spätere Export verändern keine Original-Audiodateien und überschreiben niemals ungefragt Ihre DJ-Datenbank.
  </div>
</main>
</body>
</html>"""
    output.write_text(document, encoding="utf-8")
