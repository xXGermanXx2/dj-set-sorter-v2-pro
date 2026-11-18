#!/usr/bin/env python3
"""DJ Set Sorter V2 Pro – Moderne lokale GUI für VirtualDJ und rekordbox 6/7.

Keine Cloud, keine Änderungen an Originaldateien oder Originaldatenbanken.
Rekordbox wird sicher über das offizielle XML-Format verarbeitet;
VirtualDJ wird über M3U/XML verarbeitet. Alle Originaltracks bleiben 100% unverändert.
"""
from __future__ import annotations
import copy, datetime as dt, html, json, math, os, queue, re, shutil, struct, subprocess, sys, threading, urllib.parse, wave, webbrowser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from preview import write_preview_html, format_duration

try:
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ModuleNotFoundError:
    ctk = tk = ttk = filedialog = messagebox = None

APP = "DJ Set Sorter V2 Pro"
REKORDBOX_VERSIONS = ("6", "7")
STATE_FILE = Path.home() / ".dj_set_sorter_state.json"


@dataclass
class Track:
    path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    bpm: float = 0.0
    rating: int = 0
    energy: float = 0.0
    source_id: str = ""
    audio_energy: float = 0.0
    audio_analyzed: bool = False
    analyzed_bpm: float = 0.0
    musical_key: str = ""
    key_confidence: float = 0.0
    waveform_score: float = 0.0
    intro_energy: float = 0.0
    outro_energy: float = 0.0
    breakdown_ratio: float = 0.0
    fit_score: float = 100.0
    excluded_reason: str = ""
    position_marks: list[dict] | None = None
    tempos: list[dict] | None = None
    duration: float = 210.0  # Laufzeit in Sekunden
    phase: str = ""
    camelot_key: str = ""

    @property
    def label(self) -> str:
        return f"{self.artist} – {self.title}".strip(" –") or Path(self.path).name

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration)


def attr(node, *names, default="") -> str:
    for name in names:
        if name in node.attrib and node.attrib[name] != "":
            return node.attrib[name]
    for child in node:
        for name in names:
            if name in child.attrib and child.attrib[name] != "":
                return child.attrib[name]
    return default


def number(value) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def path_from_uri(value: str) -> str:
    value = html.unescape(str(value or "")).strip()
    if value.lower().startswith("file://"):
        parsed = urllib.parse.urlparse(value)
        path = urllib.parse.unquote(parsed.path or "")
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            path = "//" + parsed.netloc + path
        if parsed.netloc.lower() == "localhost" and parsed.path == "":
            path = ""
    else:
        path = urllib.parse.unquote(value)
    if re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    if re.match(r"^[A-Za-z]:/", path):
        path = path.replace("/", "\\") if os.name == "nt" else path
    return path


def path_to_uri(path: str) -> str:
    raw = str(path or "")
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        raw = "/" + raw.replace("\\", "/")
    elif not raw.startswith("/"):
        raw = "/" + raw
    return "file://localhost" + urllib.parse.quote(raw, safe="/:\\")


# --- Camelot & Harmonisches Mixing ---

CAMELOT_MAP = {
    "1A": ("1A", "Abm / G#m", 8, "A"), "2A": ("2A", "Ebm / D#m", 3, "A"), "3A": ("3A", "Bbm / A#m", 10, "A"),
    "4A": ("4A", "Fm", 5, "A"), "5A": ("5A", "Cm", 0, "A"), "6A": ("6A", "Gm", 7, "A"),
    "7A": ("7A", "Dm", 2, "A"), "8A": ("8A", "Am", 9, "A"), "9A": ("9A", "Em", 4, "A"),
    "10A": ("10A", "Bm", 11, "A"), "11A": ("11A", "F#m", 6, "A"), "12A": ("12A", "C#m / Dbm", 1, "A"),
    "1B": ("1B", "B", 11, "B"), "2B": ("2B", "F# / Gb", 6, "B"), "3B": ("3B", "Db / C#", 1, "B"),
    "4B": ("4B", "Ab / G#", 8, "B"), "5B": ("5B", "Eb / D#", 3, "B"), "6B": ("6B", "Bb / A#", 10, "B"),
    "7B": ("7B", "F", 5, "B"), "8B": ("8B", "C", 0, "B"), "9B": ("9B", "G", 7, "B"),
    "10B": ("10B", "D", 2, "B"), "11B": ("11B", "A", 9, "B"), "12B": ("12B", "E", 4, "B")
}

NOTE_TO_CAMELOT = {
    "G#M": "1A", "ABM": "1A", "G#MIN": "1A", "ABMIN": "1A", "G# MINOR": "1A", "AB MINOR": "1A",
    "D#M": "2A", "EBM": "2A", "D#MIN": "2A", "EBMIN": "2A", "D# MINOR": "2A", "EB MINOR": "2A",
    "A#M": "3A", "BBM": "3A", "A#MIN": "3A", "BBMIN": "3A", "A# MINOR": "3A", "BB MINOR": "3A",
    "FM": "4A", "FMIN": "4A", "F MINOR": "4A",
    "CM": "5A", "CMIN": "5A", "C MINOR": "5A",
    "GM": "6A", "GMIN": "6A", "G MINOR": "6A",
    "DM": "7A", "DMIN": "7A", "D MINOR": "7A",
    "AM": "8A", "AMIN": "8A", "A MINOR": "8A",
    "EM": "9A", "EMIN": "9A", "E MINOR": "9A",
    "BM": "10A", "BMIN": "10A", "B MINOR": "10A",
    "F#M": "11A", "GBM": "11A", "F#MIN": "11A", "GBMIN": "11A", "F# MINOR": "11A", "GB MINOR": "11A",
    "C#M": "12A", "DBM": "12A", "C#MIN": "12A", "DBMIN": "12A", "C# MINOR": "12A", "DB MINOR": "12A",
    "B": "1B", "BMAJ": "1B", "B MAJOR": "1B",
    "F#": "2B", "GB": "2B", "F#MAJ": "2B", "GBMAJ": "2B", "F# MAJOR": "2B", "GB MAJOR": "2B",
    "DB": "3B", "C#": "3B", "DBMAJ": "3B", "C#MAJ": "3B", "DB MAJOR": "3B", "C# MAJOR": "3B",
    "AB": "4B", "G#": "4B", "ABMAJ": "4B", "G#MAJ": "4B", "AB MAJOR": "4B", "G# MAJOR": "4B",
    "EB": "5B", "D#": "5B", "EBMAJ": "5B", "D#MAJ": "5B", "EB MAJOR": "5B", "D# MAJOR": "5B",
    "BB": "6B", "A#": "6B", "BBMAJ": "6B", "A#MAJ": "6B", "BB MAJOR": "6B", "A# MAJOR": "6B",
    "F": "7B", "FMAJ": "7B", "F MAJOR": "7B",
    "C": "8B", "CMAJ": "8B", "C MAJOR": "8B",
    "G": "9B", "GMAJ": "9B", "G MAJOR": "9B",
    "D": "10B", "DMAJ": "10B", "D MAJOR": "10B",
    "A": "11B", "AMAJ": "11B", "A MAJOR": "11B",
    "E": "12B", "EMAJ": "12B", "E MAJOR": "12B"
}


def parse_key(raw: str) -> tuple[str, str, int, str] | None:
    raw = str(raw or "").strip().upper()
    if not raw:
        return None
    m = re.match(r"^0?([1-9]|1[0-2])([AB])$", raw)
    if m:
        code = f"{int(m.group(1))}{m.group(2)}"
        return CAMELOT_MAP.get(code)
    clean = raw.replace("♭", "B").replace("♯", "#").strip()
    if clean in NOTE_TO_CAMELOT:
        return CAMELOT_MAP.get(NOTE_TO_CAMELOT[clean])
    m2 = re.match(r"^([A-G][#B]?)\s*(M|MIN|MINOR|MAJ|MAJOR)?$", clean)
    if m2:
        note, mode = m2.group(1), m2.group(2) or ""
        key = f"{note}{mode}"
        if key in NOTE_TO_CAMELOT:
            return CAMELOT_MAP.get(NOTE_TO_CAMELOT[key])
        if note in NOTE_TO_CAMELOT:
            return CAMELOT_MAP.get(NOTE_TO_CAMELOT[note])
    return None


def get_camelot_display(raw_key: str) -> str:
    info = parse_key(raw_key)
    if info:
        return f"{info[0]} ({info[1]})"
    return str(raw_key or "–")


def key_compatibility(previous: Track, current: Track) -> float:
    p_info = parse_key(previous.musical_key)
    c_info = parse_key(current.musical_key)
    if not p_info or not c_info:
        a, b = _key_number(previous.musical_key), _key_number(current.musical_key)
        if a is None or b is None:
            return 70.0
        distance = min((a - b) % 12, (b - a) % 12)
        return 100.0 if distance == 0 else 90.0 if distance in (1, 2, 5, 7) else 45.0

    p_code, _, _, p_mode = p_info
    c_code, _, _, c_mode = c_info
    p_num = int(p_code[:-1])
    c_num = int(c_code[:-1])

    if p_code == c_code:
        return 100.0
    if p_num == c_num and p_mode != c_mode:
        return 95.0
    diff = min(abs(p_num - c_num), 12 - abs(p_num - c_num))
    if diff == 1 and p_mode == c_mode:
        return 90.0
    if diff == 1 and p_mode != c_mode:
        return 80.0
    if diff == 2:
        return 75.0
    return 40.0


def key_transition_label(previous: Track | None, current: Track) -> tuple[float, str]:
    if not previous:
        return 100.0, "Start-Track"
    score = key_compatibility(previous, current)
    if score >= 99:
        return score, "✅ Gleiche Tonart (100%)"
    if score >= 94:
        return score, "✨ Relativ Dur/Moll (95%)"
    if score >= 89:
        return score, "🔄 Camelot ±1 (90%)"
    if score >= 79:
        return score, "🔀 Diagonal (80%)"
    if score >= 74:
        return score, "⚡ Energy Boost (+2)"
    if score >= 65:
        return score, "⚖️ Neutral / Unbekannt"
    return score, "⚠️ Tonart-Sprung (40%)"


def extract_duration(node) -> float:
    for key in ("TotalTime", "SongLength", "Length", "Duration", "total_time", "song_length", "duration"):
        val = number(attr(node, key))
        if val > 0:
            return val
    return 210.0


def track_from_node(node, path_override="") -> Track:
    p = path_override or attr(node, "FilePath", "Location", "path", "file", "Name")
    p = path_from_uri(p)
    marks = [dict(x.attrib) for x in node.findall("POSITION_MARK")]
    tempos = [dict(x.attrib) for x in node.findall("TEMPO")]
    raw_key = attr(node, "Tonality", "Key", "KeyName", "key")
    dur = extract_duration(node)
    t = Track(
        path=p,
        title=attr(node, "Title", "title", "Name"),
        artist=attr(node, "Artist", "artist"),
        album=attr(node, "Album", "album"),
        genre=attr(node, "Genre", "genre"),
        bpm=number(attr(node, "BPM", "AverageBpm", "Tempo", "bpm")),
        musical_key=raw_key,
        rating=int(round(number(attr(node, "Rating", "rating")) / 51)) if number(attr(node, "Rating", "rating")) > 5 else int(number(attr(node, "Rating", "rating"))),
        source_id=attr(node, "ID", "TrackID", "id"),
        position_marks=marks,
        tempos=tempos,
        duration=dur
    )
    t.camelot_key = get_camelot_display(raw_key)
    return t


def parse_virtualdj(database: Path, playlist_files: list[Path]) -> tuple[list[Track], dict[str, list[Track]]]:
    root = ET.parse(database).getroot()
    by_path = {}
    for n in root.iter():
        if n.tag.lower().endswith("song") or any(k in n.attrib for k in ("FilePath", "Location")):
            t = track_from_node(n)
            if t.path:
                by_path[os.path.normcase(os.path.normpath(t.path))] = t
    playlists = {}
    for pf in playlist_files:
        tracks = []
        if pf.suffix.lower() == ".m3u":
            for line in pf.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    if not os.path.isabs(line):
                        line = str((pf.parent / line).resolve())
                    tracks.append(by_path.get(os.path.normcase(os.path.normpath(line)), Track(path=line)))
        else:
            try:
                pr = ET.parse(pf).getroot()
                for n in pr.iter():
                    p = attr(n, "FilePath", "Location", "path", "file")
                    if p:
                        tracks.append(by_path.get(os.path.normcase(os.path.normpath(p)), track_from_node(n)))
            except ET.ParseError:
                pass
        if tracks:
            playlists[pf.stem] = unique_tracks(tracks)
    if not playlists and by_path:
        playlists["Alle Tracks aus Datenbank"] = list(by_path.values())
    return list(by_path.values()), playlists


def virtualdj_playlist_candidates(database: Path) -> list[Path]:
    ignored_names = {
        "database.xml", "foldercache.xml", "foldercontent.xml", "history.xml",
        "searchdb.xml", "settings.xml", "playlists.xml"
    }
    candidates = []
    parent = database.parent
    dirs_to_check = [parent]
    for sub in ("My Lists", "Playlists", "Lists", "Crates"):
        p = parent / sub
        if p.is_dir():
            dirs_to_check.append(p)

    seen = set()
    for d in dirs_to_check:
        try:
            for item in d.iterdir():
                if not item.is_file() or item.name.lower() in ignored_names:
                    continue
                if item.suffix.lower() in (".m3u", ".xml"):
                    rp = item.resolve()
                    if rp != database.resolve() and rp not in seen:
                        seen.add(rp)
                        candidates.append(item)
        except (OSError, PermissionError):
            continue
    return candidates


def parse_rekordbox_xml(xml_file: Path) -> tuple[list[Track], dict[str, list[Track]]]:
    root = ET.parse(xml_file).getroot()
    by_id = {}
    for n in root.iter("TRACK"):
        t = track_from_node(n, attr(n, "Location"))
        if t.path:
            by_id[attr(n, "TrackID", "ID", default=str(len(by_id)))] = t
    playlists = {}
    for p in root.iter("NODE"):
        name = attr(p, "Name", default="Playlist")
        tracks = [by_id.get(attr(x, "Key")) for x in p.iter("TRACK")]
        if tracks and attr(p, "Type") in ("0", "1"):
            playlists[name] = unique_tracks([x for x in tracks if x])
    if not playlists and by_id:
        playlists["Alle Tracks aus XML"] = list(by_id.values())
    return list(by_id.values()), playlists


def unique_tracks(tracks: list[Track]) -> list[Track]:
    out, seen = [], set()
    for t in tracks:
        key = os.path.normcase(os.path.normpath(t.path))
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


GENRE_SCORE = {
    "ambient": 10, "chill": 15, "deep": 25, "house": 42, "disco": 45, "funk": 48,
    "tech house": 58, "progressive": 60, "trance": 68, "electro": 72, "techno": 78,
    "hard techno": 92, "hardstyle": 96, "drum & bass": 88, "dnb": 88, "gabber": 100
}


def energy_score(t: Track, position: float = 0.0) -> float:
    bpm_score = max(0, min(100, (t.bpm - 80) * 1.25)) if t.bpm else 50
    genre = t.genre.lower()
    genre_score = max((v for k, v in GENRE_SCORE.items() if k in genre), default=50)
    rating_score = min(100, t.rating * 20) if t.rating else 50
    return round(bpm_score * .45 + genre_score * .40 + rating_score * .15, 2)


KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def _goertzel(samples, frequency, sample_rate):
    if not samples or frequency <= 0 or frequency >= sample_rate / 2:
        return 0.0
    k = max(1, min(len(samples) // 2, round(len(samples) * frequency / sample_rate)))
    omega = 2.0 * math.pi * k / len(samples)
    coeff = 2.0 * math.cos(omega)
    q0 = q1 = q2 = 0.0
    for sample in samples:
        q0 = coeff * q1 - q2 + sample
        q2, q1 = q1, q0
    return max(0.0, q1 * q1 + q2 * q2 - coeff * q1 * q2)


def _estimate_key(samples, sample_rate):
    if len(samples) < sample_rate * 2:
        return "", 0.0
    chroma = [0.0] * 12
    window = min(len(samples), sample_rate * 8)
    starts = range(0, max(1, len(samples) - window + 1), max(1, (len(samples) - window) // 7 or 1))
    frequencies = [(midi, 440.0 * (2.0 ** ((midi - 69) / 12.0))) for midi in range(36, 97)]
    used = 0
    for start in list(starts)[:8]:
        chunk = samples[start:start + window]
        if len(chunk) < sample_rate * 2:
            continue
        stride = max(1, len(chunk) // 18000)
        chunk = chunk[::stride]
        effective_rate = sample_rate / stride
        for midi, frequency in frequencies:
            power = _goertzel(chunk, frequency, effective_rate)
            chroma[midi % 12] += math.sqrt(power)
        used += 1
    if not used or max(chroma) <= 0:
        return "", 0.0
    total = sum(chroma) or 1.0
    chroma = [x / total for x in chroma]
    results = []
    for root in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rotated = [profile[(i - root) % 12] for i in range(12)]
            mean = sum(rotated) / 12
            pmean = sum(chroma) / 12
            covariance = sum((a - mean) * (b - pmean) for a, b in zip(rotated, chroma))
            norm = math.sqrt(sum((a - mean) ** 2 for a in rotated) * sum((b - pmean) ** 2 for b in chroma)) or 1.0
            results.append((covariance / norm, root, mode))
    results.sort(reverse=True)
    best, second = results[0], results[1]
    confidence = max(0.0, min(100.0, (best[0] - second[0] + 0.15) * 220))
    return f"{KEY_NAMES[best[1]]} {'m' if best[2] == 'minor' else 'maj'}", round(confidence, 1)


def _estimate_bpm(envelope, sample_rate, hop):
    if len(envelope) < 16:
        return 0.0
    average = sum(envelope) / len(envelope)
    signal = [max(0.0, x - average) for x in envelope]
    best_lag, best_score = 0, -1.0
    for bpm in range(70, 181):
        lag = max(1, round(60.0 * sample_rate / (bpm * hop)))
        score = sum(signal[i] * signal[i - lag] for i in range(lag, len(signal)))
        if score > best_score:
            best_lag, best_score = lag, score
    return round(60.0 * sample_rate / (best_lag * hop), 1) if best_lag else 0.0


def analyze_audio(t: Track, max_seconds: int = 120) -> float:
    if t.audio_analyzed:
        return t.audio_energy
    t.audio_analyzed = True
    try:
        sample_rate, hop = 11025, 512
        cmd = ["ffmpeg", "-v", "error", "-i", t.path, "-t", str(max_seconds),
               "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1"]
        raw = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=max_seconds + 20, check=True).stdout
        samples = [x / 32768.0 for x in struct.unpack("<" + "h" * (len(raw) // 2), raw)]
        if len(samples) < sample_rate * 4:
            return 0.0
        rms = [math.sqrt(sum(x * x for x in samples[i:i + hop]) / hop)
               for i in range(0, len(samples) - hop, hop)]
        onset = [max(0.0, rms[i] - rms[i - 1]) for i in range(1, len(rms))]
        overall = math.sqrt(sum(x * x for x in samples) / len(samples))
        loudness = max(0.0, min(100.0, (20 * math.log10(max(overall, 1e-5)) + 60) * 1.67))
        dynamics = max(0.0, min(100.0, (max(rms) - min(rms)) * 220))
        transient = max(0.0, min(100.0, (sum(onset) / max(1, len(onset))) * 1200))
        bass = max(0.0, min(100.0, _goertzel(samples[::8], 100, sample_rate / 8) ** .5 * 1.8))
        t.audio_energy = round(loudness * .30 + dynamics * .15 + bass * .25 + transient * .30, 2)
        t.analyzed_bpm = _estimate_bpm(rms, sample_rate, hop)
        key, confidence = _estimate_key(samples, sample_rate)
        if key:
            t.musical_key, t.key_confidence = key, confidence
            t.camelot_key = get_camelot_display(key)
        chunks = max(1, len(rms) // 24)
        profile = [sum(rms[i:i + chunks]) / max(1, len(rms[i:i + chunks]))
                   for i in range(0, len(rms), chunks)]
        t.intro_energy = round(sum(profile[:max(1, len(profile) // 6)]) / max(1, len(profile) // 6) * 220, 1)
        t.outro_energy = round(sum(profile[-max(1, len(profile) // 6):]) / max(1, len(profile) // 6) * 220, 1)
        low = sum(1 for x in profile if x < max(profile) * .45)
        t.breakdown_ratio = round(low / max(1, len(profile)) * 100, 1)
        t.waveform_score = round(max(0.0, min(100.0, 100 - abs(t.intro_energy - t.outro_energy) * .55
                                                - t.breakdown_ratio * .15)), 1)
    except (OSError, subprocess.SubprocessError, ValueError, struct.error, ZeroDivisionError):
        t.audio_energy = 0.0
    return t.audio_energy


def combined_energy_score(t: Track, use_audio: bool = True) -> float:
    metadata = energy_score(t, 0)
    audio = analyze_audio(t) if use_audio else 0.0
    bpm = t.analyzed_bpm or t.bpm
    bpm_score = max(0, min(100, (bpm - 80) * 1.25)) if bpm else 50
    if use_audio and t.audio_analyzed and audio:
        return round(metadata * .30 + bpm_score * .15 + audio * .35 + t.waveform_score * .20, 2)
    return metadata


def _key_number(value):
    match = re.match(r"\s*([A-Ga-g])([#b♭]?)(?:\s|$)", str(value or ""))
    if not match:
        return None
    names = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    number = names[match.group(1).upper()] + (1 if match.group(2) == "#" else -1 if match.group(2) in ("b", "♭") else 0)
    return number % 12


def _transition_cost(previous: Track | None, current: Track) -> float:
    if not previous:
        return 0.0
    prev_bpm = previous.analyzed_bpm or previous.bpm
    curr_bpm = current.analyzed_bpm or current.bpm
    bpm_gap = abs(curr_bpm - prev_bpm) if prev_bpm and curr_bpm else 8.0
    if prev_bpm and curr_bpm:
        ratio = max(prev_bpm, curr_bpm) / max(1.0, min(prev_bpm, curr_bpm))
        if 1.85 <= ratio <= 2.15:
            bpm_gap *= .35
    energy_gap = abs(current.energy - previous.energy)
    key_penalty = 100.0 - key_compatibility(previous, current)
    return bpm_gap * 1.7 + energy_gap * .8 + key_penalty * .35 + abs(current.intro_energy - previous.outro_energy) * .18


# --- Set-Dramaturgie Profile ---

CURVE_PROFILES = {
    "classic_peak": {
        "title": "Klassischer Club-Bogen (Aufbau → Peak → Outro)",
        "desc": "Startet ruhig, baut stetig Energie auf, erreicht bei 60–75% den Peak und klingt tanzbar aus.",
        "icon_preview": "Aufbau ➔ Peak ➔ Outro",
        "fn": lambda x: 35.0 + 60.0 * (x / 0.65)**0.85 if x <= 0.65 else 95.0 - 50.0 * ((x - 0.65) / 0.35)**0.8,
        "phases": [
            (0.00, 0.25, "Warm-Up", "#10b981"),
            (0.25, 0.60, "Aufbau", "#3b82f6"),
            (0.60, 0.85, "Peak-Time", "#ef4444"),
            (0.85, 1.00, "Cool-Down", "#8b5cf6")
        ]
    },
    "linear_rise": {
        "title": "Linearer Aufbau (Stetige Steigerung bis Peak)",
        "desc": "Stufenlose Steigerung von Minute 1 bis zum finalen Höhepunkt am Ende des Sets.",
        "icon_preview": "Stetig steigend ➔ Finale",
        "fn": lambda x: 30.0 + 68.0 * (x**0.95),
        "phases": [
            (0.00, 0.30, "Warm-Up", "#10b981"),
            (0.30, 0.70, "Steigerung", "#3b82f6"),
            (0.70, 1.00, "Peak-Climax", "#ef4444")
        ]
    },
    "sunset_warmup": {
        "title": "Warm-Up & Sunset (Mellow Groove, sanfter Peak)",
        "desc": "Flüssiger, grooviger Vibe im mittleren Energiebereich. Keine harten Kicks, sondern melodischer Flow.",
        "icon_preview": "Sanfter Groove ➔ Sunset Peak",
        "fn": lambda x: 25.0 + 38.0 * math.sin(math.pi * x * 0.85),
        "phases": [
            (0.00, 0.25, "Intro / Chill", "#10b981"),
            (0.25, 0.75, "Groove / Drive", "#06b6d4"),
            (0.75, 1.00, "Sunset Ausklang", "#8b5cf6")
        ]
    },
    "two_waves": {
        "title": "Zwei Wellen (Peak 1 → Durchatmen → Peak 2 → Outro)",
        "desc": "Früher Peak bei ca. 35%, melodisches Durchatmen bei 55%, gefolgt vom Haupt-Peak bei ca. 80%.",
        "icon_preview": "Peak 1 ➔ Bridge ➔ Haupt-Peak 2",
        "fn": lambda x: (35.0 + 50.0 * (x / 0.35)**0.85) if x <= 0.35 else (85.0 - 25.0 * ((x - 0.35) / 0.20)) if x <= 0.55 else (60.0 + 38.0 * ((x - 0.55) / 0.25)**0.85) if x <= 0.80 else (98.0 - 53.0 * ((x - 0.80) / 0.20)**0.8),
        "phases": [
            (0.00, 0.20, "Intro", "#10b981"),
            (0.20, 0.40, "Peak 1", "#f59e0b"),
            (0.40, 0.65, "Bridge / Groove", "#06b6d4"),
            (0.65, 0.85, "Haupt-Peak 2", "#ef4444"),
            (0.85, 1.00, "Outro", "#8b5cf6")
        ]
    },
    "peak_direct": {
        "title": "Peak-Time Direct (Direkt hoher Druck & Club-Peak)",
        "desc": "Sehr kurzer Einstieg, danach direkt auf hohem Energieniveau (85–100%) für die heißeste Clubphase.",
        "icon_preview": "Sofort Power ➔ Volles Brett",
        "fn": lambda x: 75.0 + 23.0 * min(1.0, x / 0.20),
        "phases": [
            (0.00, 0.15, "Ramp-In", "#f59e0b"),
            (0.15, 0.85, "Primetime Peak", "#ef4444"),
            (0.85, 1.00, "Final Slam", "#dc2626")
        ]
    },
    "classic_ramp": {
        "title": "3-Zonen-Rampe (Aufbau 45% · Steigerung 37% · Peak 18%)",
        "desc": "Klassische bewährte Zonen-Aufteilung mit weichen Übergängen und BPM-Glättung.",
        "icon_preview": "Aufbau ➔ Steigerung ➔ Peak",
        "fn": lambda x: 30.0 + 65.0 * x,
        "phases": [
            (0.00, 0.45, "Aufbau", "#10b981"),
            (0.45, 0.82, "Steigerung", "#f59e0b"),
            (0.82, 1.00, "Peak", "#ef4444")
        ]
    }
}


def get_phase_for_position(curve_key: str, pos: float) -> str:
    profile = CURVE_PROFILES.get(curve_key, CURVE_PROFILES["classic_peak"])
    phases = profile.get("phases", [])
    for start, end, name, _ in phases:
        if start <= pos <= end:
            return name
    return phases[-1][2] if phases else "Set"


def generate_new_set(
    tracks: list[Track],
    curve_key: str = "classic_peak",
    target_minutes: float | None = 60.0,
    tolerance_minutes: float = 5.0,
    use_audio: bool = True,
    prefer_camelot: bool = True,
    smooth_bpm: bool = True,
    exclude_incompatible: bool = False
) -> tuple[list[Track], dict]:
    if not tracks:
        return [], {}

    for t in tracks:
        t.excluded_reason = ""
        t.energy = energy_score(t, 0)
        if not t.camelot_key:
            t.camelot_key = get_camelot_display(t.musical_key)
        if not getattr(t, "duration", 0.0) or t.duration <= 0:
            t.duration = 210.0

    profile = CURVE_PROFILES.get(curve_key, CURVE_PROFILES["classic_peak"])
    curve_fn = profile["fn"]

    candidates = list(tracks)
    if exclude_incompatible and len(candidates) > 2:
        median_bpm = sorted((t.analyzed_bpm or t.bpm) for t in candidates if (t.analyzed_bpm or t.bpm))
        median_bpm = median_bpm[len(median_bpm) // 2] if median_bpm else 0
        for t in candidates[:]:
            bpm = t.analyzed_bpm or t.bpm
            ratio = max(bpm, median_bpm) / max(1.0, min(bpm, median_bpm)) if bpm and median_bpm else 1.0
            outlier = bool(median_bpm and bpm and abs(bpm - median_bpm) > max(18, median_bpm * .18))
            half_or_double = 1.85 <= ratio <= 2.15
            if outlier and not half_or_double:
                t.fit_score = 25.0
                t.excluded_reason = "BPM-Ausreißer ohne kompatibles Halb-/Doppeltempo"
                candidates.remove(t)
        if not candidates:
            candidates = list(tracks)

    target_sec = (target_minutes * 60.0) if (target_minutes and target_minutes > 0) else None
    tol_sec = max(60.0, tolerance_minutes * 60.0)

    pool_total_sec = sum(t.duration for t in candidates)
    if target_sec is None or target_sec <= 0 or target_sec >= pool_total_sec:
        ordered = []
        rem = list(candidates)
        n = len(rem)
        previous = None
        for i in range(n):
            norm_pos = i / max(1, n - 1)
            target_e = curve_fn(norm_pos)
            choice = min(
                rem,
                key=lambda x: (
                    abs(x.energy - target_e) * 1.3
                    + (_transition_cost(previous, x) if previous else abs(x.energy - target_e) * 0.5)
                )
            )
            choice.phase = get_phase_for_position(curve_key, norm_pos)
            rem.remove(choice)
            ordered.append(choice)
            previous = choice

        total_dur = sum(t.duration for t in ordered)
        info = {
            "curve_key": curve_key,
            "curve_title": profile["title"],
            "total_duration": total_dur,
            "formatted_duration": format_duration(total_dur),
            "target_duration": target_sec or total_dur,
            "track_count": len(ordered),
            "pool_count": len(tracks),
            "diff_sec": 0.0
        }
        return ordered, info

    beam = [([], 0.0, 0.0)]
    best_completed = None
    best_score = float("inf")

    for _ in range(50):
        next_beam = []
        any_expanded = False
        for path, cur_time, score in beam:
            if cur_time >= target_sec - tol_sec:
                diff = abs(cur_time - target_sec)
                final_score = (score / max(1, len(path))) + (diff / 60.0) * 1.5
                if final_score < best_score:
                    best_score = final_score
                    best_completed = (path, cur_time, final_score)
                continue

            used_paths = {t.path for t in path}
            avail = [t for t in candidates if t.path not in used_paths]
            if not avail:
                continue

            pos = min(1.0, max(0.0, (cur_time + 120.0) / target_sec))
            ideal_e = curve_fn(pos)
            prev = path[-1] if path else None

            candidate_costs = []
            for t in avail:
                e_diff = abs(t.energy - ideal_e)
                t_cost = _transition_cost(prev, t) if prev else (abs(t.energy - ideal_e) * 0.5)
                overshoot = max(0.0, (cur_time + t.duration) - (target_sec + tol_sec))
                cost = e_diff * 1.2 + t_cost * 0.8 + (overshoot / 30.0) * 60.0
                candidate_costs.append((cost, t))

            candidate_costs.sort(key=lambda x: x[0])
            for cost, t in candidate_costs[:5]:
                if cur_time + t.duration <= target_sec + tol_sec or cur_time < target_sec - tol_sec:
                    next_beam.append((path + [t], cur_time + t.duration, score + cost))
                    any_expanded = True

        if not any_expanded or not next_beam:
            break
        next_beam.sort(key=lambda x: x[2] / max(1, len(x[0])))
        beam = next_beam[:7]

    if best_completed:
        chosen_tracks, total_dur, _ = best_completed
    elif beam:
        best = min(beam, key=lambda x: abs(x[1] - target_sec))
        chosen_tracks, total_dur, _ = best
    else:
        chosen_tracks = candidates[:10]
        total_dur = sum(t.duration for t in chosen_tracks)

    set_len = len(chosen_tracks)
    for i, t in enumerate(chosen_tracks):
        norm_pos = i / max(1, set_len - 1) if set_len > 1 else 0.5
        t.phase = get_phase_for_position(curve_key, norm_pos)

    info = {
        "curve_key": curve_key,
        "curve_title": profile["title"],
        "total_duration": total_dur,
        "formatted_duration": format_duration(total_dur),
        "target_duration": target_sec,
        "track_count": len(chosen_tracks),
        "pool_count": len(tracks),
        "diff_sec": total_dur - target_sec
    }
    return chosen_tracks, info


def sort_for_set(tracks: list[Track], ramp: float = 1.0, use_audio: bool = True,
                 exclude_incompatible: bool = False, curve: str = "classic_ramp",
                 target_duration_minutes: float | None = None) -> list[Track]:
    if not tracks:
        return []
    if target_duration_minutes or (curve != "classic_ramp" and curve in CURVE_PROFILES):
        res, _ = generate_new_set(
            tracks, curve_key=curve, target_minutes=target_duration_minutes,
            use_audio=use_audio, exclude_incompatible=exclude_incompatible
        )
        return res

    for t in tracks:
        t.excluded_reason = ""
        t.energy = combined_energy_score(t, use_audio)
    candidates = list(tracks)
    if exclude_incompatible and len(candidates) > 2:
        median_bpm = sorted((t.analyzed_bpm or t.bpm) for t in candidates if (t.analyzed_bpm or t.bpm))
        median_bpm = median_bpm[len(median_bpm) // 2] if median_bpm else 0
        for t in candidates[:]:
            bpm = t.analyzed_bpm or t.bpm
            ratio = max(bpm, median_bpm) / max(1.0, min(bpm, median_bpm)) if bpm and median_bpm else 1.0
            outlier = bool(median_bpm and bpm and abs(bpm - median_bpm) > max(18, median_bpm * .18))
            half_or_double = 1.85 <= ratio <= 2.15
            if outlier and not half_or_double:
                t.fit_score = 25.0
                t.excluded_reason = "BPM-Ausreißer ohne kompatibles Halb-/Doppeltempo"
                candidates.remove(t)
        if not candidates:
            candidates = list(tracks)
    candidates.sort(key=lambda x: (x.energy, x.analyzed_bpm or x.bpm or 0))
    n = len(candidates)
    zones = [
        candidates[:max(1, round(n * .45))],
        candidates[max(1, round(n * .45)):max(1, round(n * .82))],
        candidates[max(1, round(n * .82)):]
    ]
    ordered = []
    previous = None
    for zone_index, zone in enumerate(zones):
        while zone:
            target = ordered[-1].energy + (5.0 if ordered else 0.0) if ordered else min(x.energy for x in zone)
            choice = min(
                zone,
                key=lambda x: (
                    _transition_cost(previous, x) + abs(x.energy - target) * (1.2 if zone_index < 2 else .6)
                ) if previous else x.energy
            )
            zone.remove(choice)
            ordered.append(choice)
            previous = choice
    return ordered


def backup_database(path: Path, program: str) -> Path:
    target = Path.home() / "Documents" / "database backup" / program / dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, target / path.name, dirs_exist_ok=True)
    else:
        shutil.copy2(path, target / path.name)
    return target


def write_virtualdj_m3u(tracks: list[Track], output: Path) -> None:
    output.write_text("#EXTM3U\n" + "\n".join(t.path for t in tracks) + "\n", encoding="utf-8")


def write_rekordbox_xml(tracks: list[Track], name: str, output: Path) -> None:
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name="rekordbox", Version="7")
    collection = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks)))
    for i, t in enumerate(tracks, 1):
        dur_val = str(int(round(t.duration))) if getattr(t, "duration", 0) > 0 else ""
        track_node = ET.SubElement(
            collection, "TRACK", TrackID=str(i),
            Name=t.title or Path(t.path).stem,
            Artist=t.artist, Album=t.album, Genre=t.genre,
            AverageBpm=str(t.analyzed_bpm or t.bpm or ""),
            Rating=str(min(255, max(0, t.rating * 51))),
            Comments=f"DJ Set Sorter Reihenfolge: {i:02d} | Phase: {t.phase or 'Set'}",
            Location=path_to_uri(t.path)
        )
        if dur_val:
            track_node.set("TotalTime", dur_val)
        if t.musical_key:
            track_node.set("Tonality", t.musical_key)
        for mark in (t.position_marks or []):
            ET.SubElement(track_node, "POSITION_MARK", **{str(k): str(v) for k, v in mark.items()})
        for tempo in (t.tempos or []):
            ET.SubElement(track_node, "TEMPO", **{str(k): str(v) for k, v in tempo.items()})
    playlists = ET.SubElement(root, "PLAYLISTS")
    root_node = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")
    pl = ET.SubElement(root_node, "NODE", Type="1", Name=name, KeyType="0", Entries=str(len(tracks)))
    for i in range(1, len(tracks) + 1):
        ET.SubElement(pl, "TRACK", Key=str(i))
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)


def autodetect(program: str) -> Path | None:
    home = Path.home()
    if program == "VirtualDJ":
        candidates = [home / "Documents/VirtualDJ/database.xml", home / "AppData/Local/VirtualDJ/database.xml"]
        return next((p for p in candidates if p.exists()), None)
    candidates = [
        home / "Documents/rekordbox/rekordbox.xml",
        home / "Documents/Pioneer/rekordbox/rekordbox.xml",
        home / "Library/Pioneer/rekordbox/rekordbox.xml"
    ]
    return next((p for p in candidates if p.exists()), None)


# --- Moderne GUI Anwendung mit CustomTkinter ---

class App(ctk.CTk if ctk else object):
    def __init__(self, root=None):
        if ctk is None:
            raise RuntimeError("CustomTkinter fehlt. Installieren mit: pip install customtkinter")
        super().__init__()
        self.root = self

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title(APP)
        self.geometry("1260x840")
        self.minsize(1080, 720)

        # State Variablen
        self.program_var = tk.StringVar(value=f"rekordbox {REKORDBOX_VERSIONS[0]}/{REKORDBOX_VERSIONS[1]}")
        self.db_path_var = tk.StringVar()
        self.backup_var = tk.BooleanVar(value=True)
        self.audio_var = tk.BooleanVar(value=True)
        self.prefer_camelot_var = tk.BooleanVar(value=True)
        self.smooth_bpm_var = tk.BooleanVar(value=True)
        self.exclude_incompatible_var = tk.BooleanVar(value=False)
        self.backup_status_var = tk.StringVar(value="Kein Backup vorhanden.")
        self.backup_state = self._read_backup_state()

        # Tab 1 State
        self.tab1_selected_playlist = tk.StringVar(value="[ Alle Tracks ]")
        self.tab1_search_var = tk.StringVar()
        self.tab1_sort_var = tk.StringVar(value="Original / Standard")

        # Tab 2 State
        self.tab2_selected_playlist = tk.StringVar(value="[ Alle Tracks ]")
        self.tab2_curve_key = "classic_peak"
        self.tab2_length_preset = tk.StringVar(value="60 Minuten (1 Stunde)")
        self.tab2_custom_min = tk.StringVar(value="60")
        self.tab2_set_name = tk.StringVar(value="Mein Set – 60 Min")

        # Daten
        self.all_tracks: list[Track] = []
        self.playlists: dict[str, list[Track]] = {}
        self.current_set_tracks: list[Track] = []
        self.current_set_info: dict = {}

        # Threading Queue
        self.task_queue = queue.Queue()
        self._poll_task_queue()

        self._configure_treeview_styles()
        self._build_ui()

        # Automatische Erkennung
        detected = autodetect("rekordbox")
        if detected:
            self.db_path_var.set(str(detected))
        self._refresh_backup_status()

    def dispatch_to_main(self, func, *args, **kwargs) -> None:
        self.task_queue.put((func, args, kwargs))

    def _poll_task_queue(self) -> None:
        try:
            while True:
                func, args, kwargs = self.task_queue.get_nowait()
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    print("Fehler beim Ausführen der UI-Aufgabe:", e)
        except queue.Empty:
            pass
        self.after(40, self._poll_task_queue)

    def _read_backup_state(self) -> dict:
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_backup_state(self) -> None:
        try:
            STATE_FILE.write_text(json.dumps(self.backup_state, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _refresh_backup_status(self) -> None:
        prog = "VirtualDJ" if "VirtualDJ" in self.program_var.get() else "rekordbox"
        info = self.backup_state.get(prog)
        if info:
            self.backup_status_var.set(f"Letztes {prog}-Backup: {info.get('time', 'unbekannt')}")
        else:
            self.backup_status_var.set(f"Kein {prog}-Backup vorhanden.")

    def _configure_treeview_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        tree_bg = "#151821"
        tree_fg = "#f1f5f9"
        tree_head_bg = "#212634"
        tree_head_fg = "#94a3b8"
        tree_sel = "#2563eb"

        style.configure(
            "Treeview",
            background=tree_bg,
            foreground=tree_fg,
            fieldbackground=tree_bg,
            rowheight=28,
            borderwidth=0,
            font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading",
            background=tree_head_bg,
            foreground=tree_head_fg,
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padding=(6, 8)
        )
        style.map(
            "Treeview",
            background=[("selected", tree_sel)],
            foreground=[("selected", "#ffffff")]
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#2d3446")],
            foreground=[("active", "#ffffff")]
        )

    def _build_ui(self) -> None:
        self.configure(fg_color="#0e1117")

        # Container
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=16, pady=14)

        # 1. Top Header
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        h_left = ctk.CTkFrame(header, fg_color="transparent")
        h_left.pack(side="left")

        lbl_logo = ctk.CTkLabel(h_left, text="🎧 DJ SET SORTER", font=ctk.CTkFont(size=20, weight="bold"), text_color="#ffffff")
        lbl_logo.pack(side="left", padx=(0, 8))

        badge_pro = ctk.CTkLabel(
            h_left, text="PRO V2", font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1d4ed8", text_color="#bfdbfe", corner_radius=6, padx=8, pady=2
        )
        badge_pro.pack(side="left", padx=(0, 10))

        lbl_sub = ctk.CTkLabel(h_left, text="· Intelligente Set-Dramaturgie & Harmonisches Mixing", font=ctk.CTkFont(size=13), text_color="#94a3b8")
        lbl_sub.pack(side="left")

        h_right = ctk.CTkFrame(header, fg_color="transparent")
        h_right.pack(side="right")

        badge_safety = ctk.CTkLabel(
            h_right, text="🛡️ 100% Sicher: Original-Audio & DBs bleiben unangetastet",
            font=ctk.CTkFont(size=12, weight="bold"), fg_color="#064e3b", text_color="#34d399",
            corner_radius=6, padx=12, pady=4
        )
        badge_safety.pack(side="right")

        # 2. Database & Source Bar
        src_card = ctk.CTkFrame(main, fg_color="#161922", corner_radius=10, border_width=1, border_color="#242b3b")
        src_card.pack(fill="x", pady=(0, 12), ipady=4)

        r1 = ctk.CTkFrame(src_card, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkLabel(r1, text="Software:", font=ctk.CTkFont(size=13, weight="bold"), text_color="#cbd5e1").pack(side="left", padx=(0, 6))
        self.prog_menu = ctk.CTkOptionMenu(
            r1, variable=self.program_var,
            values=["rekordbox 6/7", "VirtualDJ"],
            command=self._on_program_changed,
            width=140, fg_color="#222836", button_color="#2d3548", button_hover_color="#3b465e"
        )
        self.prog_menu.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(r1, text="Datenbank / XML:", font=ctk.CTkFont(size=13), text_color="#cbd5e1").pack(side="left", padx=(0, 6))
        self.entry_db = ctk.CTkEntry(
            r1, textvariable=self.db_path_var,
            placeholder_text="Pfad zur XML- oder Datenbankdatei...",
            fg_color="#0f1118", border_color="#2d3548"
        )
        self.entry_db.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            r1, text="Durchsuchen…", width=110,
            fg_color="#2d3548", hover_color="#3c4760",
            command=self.choose_db
        ).pack(side="left", padx=(0, 8))

        self.btn_load = ctk.CTkButton(
            r1, text="📥 Bibliothek laden", width=150,
            fg_color="#2563eb", hover_color="#1d4ed8", font=ctk.CTkFont(size=13, weight="bold"),
            command=self.load_library
        )
        self.btn_load.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            r1, text="Sichern", width=80,
            fg_color="#2d3548", hover_color="#3c4760",
            command=self.manual_backup
        ).pack(side="left")

        r2 = ctk.CTkFrame(src_card, fg_color="transparent")
        r2.pack(fill="x", padx=12, pady=(0, 8))

        self.lbl_src_status = ctk.CTkLabel(r2, text="Noch keine Bibliothek geladen.", font=ctk.CTkFont(size=12), text_color="#94a3b8")
        self.lbl_src_status.pack(side="left")

        self.lbl_backup_status = ctk.CTkLabel(r2, textvariable=self.backup_status_var, font=ctk.CTkFont(size=12), text_color="#64748b")
        self.lbl_backup_status.pack(side="right")

        # 3. Main Tabs (CTkTabview)
        self.tabview = ctk.CTkTabview(main, fg_color="#161922", segmented_button_selected_color="#2563eb", segmented_button_fg_color="#0f1118")
        self.tabview.pack(fill="both", expand=True)

        self.tab_all = self.tabview.add("📋 Alle Tracks")
        self.tab_set = self.tabview.add("🎧 Neues Set (Energie-Dramaturgie)")

        self._build_tab_all_tracks()
        self._build_tab_new_set()

        # 4. Bottom Global Status
        footer = ctk.CTkFrame(main, fg_color="transparent")
        footer.pack(fill="x", pady=(8, 0))

        self.status_var = tk.StringVar(value="Bereit. Original-Dateien werden niemals verändert.")
        ctk.CTkLabel(footer, textvariable=self.status_var, font=ctk.CTkFont(size=12), text_color="#38bdf8").pack(side="left")

    # ================= TAB 1: ALLE TRACKS =================

    def _build_tab_all_tracks(self) -> None:
        tab = self.tab_all

        # Toolbar
        bar = ctk.CTkFrame(tab, fg_color="#10131a", corner_radius=8, border_width=1, border_color="#242b3b")
        bar.pack(fill="x", padx=6, pady=(6, 10), ipady=4)

        bar_inner = ctk.CTkFrame(bar, fg_color="transparent")
        bar_inner.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(bar_inner, text="Playlist:", font=ctk.CTkFont(weight="bold"), text_color="#cbd5e1").pack(side="left", padx=(0, 6))
        self.tab1_menu_playlist = ctk.CTkOptionMenu(
            bar_inner, variable=self.tab1_selected_playlist,
            values=["[ Alle Tracks ]"], command=lambda v: self._refresh_tab1_tracks(),
            width=180, fg_color="#222836", button_color="#2d3548"
        )
        self.tab1_menu_playlist.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(bar_inner, text="Suche:", text_color="#cbd5e1").pack(side="left", padx=(0, 6))
        self.entry_tab1_search = ctk.CTkEntry(
            bar_inner, textvariable=self.tab1_search_var,
            placeholder_text="Titel, Interpret, Key, BPM...",
            width=200, fg_color="#161922", border_color="#2d3548"
        )
        self.entry_tab1_search.pack(side="left", padx=(0, 16))
        self.entry_tab1_search.bind("<KeyRelease>", lambda e: self._refresh_tab1_tracks())

        ctk.CTkLabel(bar_inner, text="Sortierung:", text_color="#cbd5e1").pack(side="left", padx=(0, 6))
        self.tab1_menu_sort = ctk.CTkOptionMenu(
            bar_inner, variable=self.tab1_sort_var,
            values=[
                "Original / Standard",
                "⚡ Intelligente Set-Dramaturgie",
                "📈 Energie aufsteigend",
                "📉 Energie absteigend",
                "🎵 BPM aufsteigend",
                "🎵 BPM absteigend",
                "🎹 Tonart (Camelot)",
                "🔤 Titel (A-Z)",
                "👤 Interpret (A-Z)"
            ],
            command=lambda v: self._refresh_tab1_tracks(),
            width=230, fg_color="#222836", button_color="#2d3548"
        )
        self.tab1_menu_sort.pack(side="left", padx=(0, 16))

        self.lbl_tab1_count = ctk.CTkLabel(bar_inner, text="0 Tracks", font=ctk.CTkFont(size=12), text_color="#94a3b8")
        self.lbl_tab1_count.pack(side="right")

        # Treeview Frame
        table_container = ctk.CTkFrame(tab, fg_color="#10131a", corner_radius=8, border_width=1, border_color="#242b3b")
        table_container.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        cols = ("num", "title", "artist", "dur", "bpm", "key", "energy", "genre", "path")
        self.tree_all = ttk.Treeview(table_container, columns=cols, show="headings", selectmode="extended")
        self.tree_all.heading("num", text="#")
        self.tree_all.heading("title", text="Titel")
        self.tree_all.heading("artist", text="Interpret")
        self.tree_all.heading("dur", text="Dauer")
        self.tree_all.heading("bpm", text="BPM")
        self.tree_all.heading("key", text="Tonart (Camelot)")
        self.tree_all.heading("energy", text="Energie")
        self.tree_all.heading("genre", text="Genre")
        self.tree_all.heading("path", text="Dateipfad")

        self.tree_all.column("num", width=40, anchor="center")
        self.tree_all.column("title", width=220)
        self.tree_all.column("artist", width=180)
        self.tree_all.column("dur", width=70, anchor="center")
        self.tree_all.column("bpm", width=70, anchor="center")
        self.tree_all.column("key", width=120, anchor="center")
        self.tree_all.column("energy", width=70, anchor="center")
        self.tree_all.column("genre", width=120)
        self.tree_all.column("path", width=300)

        scroll = ttk.Scrollbar(table_container, orient="vertical", command=self.tree_all.yview)
        self.tree_all.configure(yscrollcommand=scroll.set)
        self.tree_all.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        scroll.pack(side="right", fill="y", padx=2, pady=2)

        # Action Buttons
        act_bar = ctk.CTkFrame(tab, fg_color="transparent")
        act_bar.pack(fill="x", padx=6, pady=(0, 6))

        ctk.CTkButton(
            act_bar, text="🌐 HTML-Vorschau öffnen", width=180,
            fg_color="#222836", hover_color="#2d3548", command=self.preview_tab1
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            act_bar, text="💾 Alle Tracks exportieren", width=190,
            fg_color="#10b981", hover_color="#059669", font=ctk.CTkFont(weight="bold"),
            command=self.export_tab1
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            act_bar, text="➡️ In 'Neues Set' übernehmen", width=210,
            fg_color="#2563eb", hover_color="#1d4ed8", command=self.send_tab1_to_tab2
        ).pack(side="left")

    # ================= TAB 2: NEUES SET =================

    def _build_tab_new_set(self) -> None:
        tab = self.tab_set

        # Split: Links Konfiguration (Scrollable), Rechts Ergebnis
        content = ctk.CTkFrame(tab, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=4, pady=4)

        # Linke Spalte (Scrollable Frame)
        left = ctk.CTkScrollableFrame(
            content, width=390, fg_color="#10131a", corner_radius=10,
            border_width=1, border_color="#242b3b"
        )
        left.pack(side="left", fill="both", padx=(0, 10), pady=0)

        # Rechte Spalte (Ergebnis & Tabelle)
        right = ctk.CTkFrame(content, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True)

        # --- Linke Widgets ---

        # 1. Quell-Playlist
        card1 = self._make_card(left, "1. Quell-Playlist wählen")
        self.tab2_menu_playlist = ctk.CTkOptionMenu(
            card1, variable=self.tab2_selected_playlist,
            values=["[ Alle Tracks ]"], command=lambda v: self._on_tab2_playlist_changed(),
            fg_color="#1e2433", button_color="#2a3347"
        )
        self.tab2_menu_playlist.pack(fill="x", padx=10, pady=(6, 4))
        self.lbl_tab2_pool_info = ctk.CTkLabel(card1, text="Pool: 0 Tracks verfügbar", font=ctk.CTkFont(size=12), text_color="#94a3b8")
        self.lbl_tab2_pool_info.pack(anchor="w", padx=10, pady=(0, 8))

        # 2. Set-Aufbau / Energie-Kurve
        card2 = self._make_card(left, "2. Set-Aufbau & Energie-Kurve")
        curve_titles = [v["title"] for v in CURVE_PROFILES.values()]
        self.tab2_curve_menu = ctk.CTkOptionMenu(
            card2, values=curve_titles,
            command=self._on_curve_menu_changed,
            fg_color="#1e2433", button_color="#2a3347"
        )
        self.tab2_curve_menu.pack(fill="x", padx=10, pady=(6, 6))

        # Mini Canvas für Live-Kurven-Grafik
        self.curve_canvas = tk.Canvas(card2, width=330, height=48, bg="#161922", highlightthickness=0)
        self.curve_canvas.pack(fill="x", padx=10, pady=(0, 6))

        self.lbl_curve_desc = ctk.CTkLabel(card2, text="", font=ctk.CTkFont(size=12), text_color="#94a3b8", wraplength=340, justify="left")
        self.lbl_curve_desc.pack(anchor="w", padx=10, pady=(0, 8))

        # 3. Gewünschte Set-Länge
        card3 = self._make_card(left, "3. Gewünschte Set-Länge")
        length_options = [
            "30 Minuten (~7–9 Tracks)",
            "45 Minuten (~10–13 Tracks)",
            "60 Minuten (1 Stunde) [Standard]",
            "90 Minuten (1,5 Stunden)",
            "120 Minuten (2 Stunden)",
            "Alle Tracks verwenden (Kein Zeitlimit)",
            "Benutzerdefiniert"
        ]
        self.tab2_menu_length = ctk.CTkOptionMenu(
            card3, variable=self.tab2_length_preset,
            values=length_options, command=self._on_length_preset_changed,
            fg_color="#1e2433", button_color="#2a3347"
        )
        self.tab2_menu_length.pack(fill="x", padx=10, pady=(6, 4))

        self.frame_custom_dur = ctk.CTkFrame(card3, fg_color="transparent")
        ctk.CTkLabel(self.frame_custom_dur, text="Minuten:", text_color="#cbd5e1").pack(side="left", padx=(0, 6))
        self.entry_custom_min = ctk.CTkEntry(self.frame_custom_dur, textvariable=self.tab2_custom_min, width=80, fg_color="#161922")
        self.entry_custom_min.pack(side="left")
        self.frame_custom_dur.pack(fill="x", padx=10, pady=(2, 4))
        self.frame_custom_dur.pack_forget()

        ctk.CTkLabel(card3, text="Toleranz: ca. ±5 Min. (wählt optimale Teilmenge)", font=ctk.CTkFont(size=11), text_color="#64748b").pack(anchor="w", padx=10, pady=(0, 8))

        # 4. Mixing-Optionen
        card4 = self._make_card(left, "4. Mixing & Analyse")
        ctk.CTkCheckBox(card4, text="Harmonisches Mixing priorisieren (Camelot)", variable=self.prefer_camelot_var).pack(anchor="w", padx=10, pady=4)
        ctk.CTkCheckBox(card4, text="BPM-Sprünge sanft glätten", variable=self.smooth_bpm_var).pack(anchor="w", padx=10, pady=4)
        ctk.CTkCheckBox(card4, text="Audio-Analyse (BPM, Key, Waveform-RMS)", variable=self.audio_var).pack(anchor="w", padx=10, pady=4)
        ctk.CTkCheckBox(card4, text="Ausreißer ohne Übergang ausschließen", variable=self.exclude_incompatible_var).pack(anchor="w", padx=10, pady=4)
        ctk.CTkCheckBox(card4, text="Vorher Datenbank-Backup sichern", variable=self.backup_var).pack(anchor="w", padx=10, pady=(4, 10))

        # 5. Name der Playlist
        card5 = self._make_card(left, "5. Name der Playlist")
        self.entry_set_name = ctk.CTkEntry(card5, textvariable=self.tab2_set_name, fg_color="#161922")
        self.entry_set_name.pack(fill="x", padx=10, pady=(6, 10))

        # Big Action Button
        self.btn_generate = ctk.CTkButton(
            left, text="⚡ NEUES SET GENERIEREN", height=46,
            fg_color="#2563eb", hover_color="#1d4ed8", font=ctk.CTkFont(size=14, weight="bold"),
            command=self.generate_set_tab2
        )
        self.btn_generate.pack(fill="x", padx=4, pady=(6, 14))

        # --- Rechte Spalte: Set-Ergebnis & Tabelle ---

        # Status Banner Card
        self.card_set_status = ctk.CTkFrame(right, fg_color="#10131a", corner_radius=8, border_width=1, border_color="#242b3b")
        self.card_set_status.pack(fill="x", pady=(0, 10), ipady=4)

        status_inner = ctk.CTkFrame(self.card_set_status, fg_color="transparent")
        status_inner.pack(fill="x", padx=12, pady=8)

        self.lbl_set_title = ctk.CTkLabel(
            status_inner,
            text="Wählen Sie links Ihre gewünschte Kurve & Set-Länge und klicken Sie auf 'Set generieren'.",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#f8fafc"
        )
        self.lbl_set_title.pack(anchor="w", pady=(0, 2))

        self.lbl_set_stats = ctk.CTkLabel(status_inner, text="", font=ctk.CTkFont(size=12), text_color="#94a3b8")
        self.lbl_set_stats.pack(anchor="w")

        # Set Treeview Table
        set_table_container = ctk.CTkFrame(right, fg_color="#10131a", corner_radius=8, border_width=1, border_color="#242b3b")
        set_table_container.pack(fill="both", expand=True, pady=(0, 10))

        set_cols = ("num", "phase", "title", "artist", "dur", "bpm", "key", "harmony", "energy", "genre")
        self.tree_set = ttk.Treeview(set_table_container, columns=set_cols, show="headings", selectmode="extended")
        self.tree_set.heading("num", text="#")
        self.tree_set.heading("phase", text="Phase im Set")
        self.tree_set.heading("title", text="Titel")
        self.tree_set.heading("artist", text="Interpret")
        self.tree_set.heading("dur", text="Dauer")
        self.tree_set.heading("bpm", text="BPM")
        self.tree_set.heading("key", text="Key (Camelot)")
        self.tree_set.heading("harmony", text="Übergang / Harmonie")
        self.tree_set.heading("energy", text="Energie")
        self.tree_set.heading("genre", text="Genre")

        self.tree_set.column("num", width=35, anchor="center")
        self.tree_set.column("phase", width=95, anchor="center")
        self.tree_set.column("title", width=200)
        self.tree_set.column("artist", width=160)
        self.tree_set.column("dur", width=65, anchor="center")
        self.tree_set.column("bpm", width=65, anchor="center")
        self.tree_set.column("key", width=110, anchor="center")
        self.tree_set.column("harmony", width=170)
        self.tree_set.column("energy", width=65, anchor="center")
        self.tree_set.column("genre", width=100)

        self.tree_set.tag_configure("phase_warmup", foreground="#34d399")
        self.tree_set.tag_configure("phase_build", foreground="#60a5fa")
        self.tree_set.tag_configure("phase_peak", foreground="#f87171")
        self.tree_set.tag_configure("phase_cooldown", foreground="#c084fc")

        scroll_set = ttk.Scrollbar(set_table_container, orient="vertical", command=self.tree_set.yview)
        self.tree_set.configure(yscrollcommand=scroll_set.set)
        self.tree_set.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        scroll_set.pack(side="right", fill="y", padx=2, pady=2)

        # Action Buttons
        set_acts = ctk.CTkFrame(right, fg_color="transparent")
        set_acts.pack(fill="x")

        ctk.CTkButton(
            set_acts, text="💾 Set-Playlist exportieren", width=200,
            fg_color="#10b981", hover_color="#059669", font=ctk.CTkFont(weight="bold"),
            command=self.export_tab2
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            set_acts, text="🌐 HTML-Vorschau mit Kurven-Grafik", width=240,
            fg_color="#222836", hover_color="#2d3548", command=self.preview_tab2
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            set_acts, text="📋 Trackliste kopieren", width=160,
            fg_color="#222836", hover_color="#2d3548", command=self.copy_set_to_clipboard
        ).pack(side="left")

        # Erste Initialisierung der Kurvengrafik
        self._draw_mini_curve(CURVE_PROFILES["classic_peak"]["fn"])
        self.lbl_curve_desc.configure(text=CURVE_PROFILES["classic_peak"]["desc"])

    def _make_card(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color="#151821", corner_radius=8, border_width=1, border_color="#212735")
        card.pack(fill="x", padx=4, pady=6)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=13, weight="bold"), text_color="#cbd5e1").pack(anchor="w", padx=10, pady=(8, 2))
        return card

    # ================= EVENT HANDLERS & LOGIK =================

    def _on_program_changed(self, choice: str) -> None:
        prog = "VirtualDJ" if "VirtualDJ" in choice else "rekordbox"
        detected = autodetect(prog)
        self.db_path_var.set(str(detected or ""))
        self.playlists = {}
        self.all_tracks = []
        self._update_playlist_menus()
        self._refresh_backup_status()

    def _draw_mini_curve(self, fn) -> None:
        self.curve_canvas.delete("all")
        w, h = 330, 48
        pad_x, pad_y = 12, 8
        eff_w = w - 2 * pad_x
        eff_h = h - 2 * pad_y

        pts = []
        steps = 30
        for i in range(steps + 1):
            norm_x = i / steps
            x = pad_x + norm_x * eff_w
            e = max(0.0, min(100.0, fn(norm_x)))
            y = pad_y + eff_h * (1.0 - e / 100.0)
            pts.extend([x, y])

        # Hintergrund-Gitterlinie 50%
        mid_y = pad_y + eff_h * 0.5
        self.curve_canvas.create_line(pad_x, mid_y, w - pad_x, mid_y, fill="#212735", dash=(3, 3))

        # Kurvenlinie
        self.curve_canvas.create_line(pts, fill="#38bdf8", width=2, smooth=True)

        # Start- & Peak-Punkte
        start_y = pad_y + eff_h * (1.0 - fn(0.0) / 100.0)
        self.curve_canvas.create_oval(pad_x - 3, start_y - 3, pad_x + 3, start_y + 3, fill="#10b981", outline="")

        peak_pos = max(range(steps + 1), key=lambda i: fn(i / steps)) / steps
        peak_x = pad_x + peak_pos * eff_w
        peak_y = pad_y + eff_h * (1.0 - fn(peak_pos) / 100.0)
        self.curve_canvas.create_oval(peak_x - 3, peak_y - 3, peak_x + 3, peak_y + 3, fill="#ef4444", outline="")

        end_y = pad_y + eff_h * (1.0 - fn(1.0) / 100.0)
        self.curve_canvas.create_oval(w - pad_x - 3, end_y - 3, w - pad_x + 3, end_y + 3, fill="#8b5cf6", outline="")

    def _on_curve_menu_changed(self, choice: str) -> None:
        for k, v in CURVE_PROFILES.items():
            if v["title"] == choice:
                self.tab2_curve_key = k
                self._draw_mini_curve(v["fn"])
                self.lbl_curve_desc.configure(text=v["desc"])
                break
        dur_label = self.tab2_length_preset.get().split()[0]
        self.tab2_set_name.set(f"Set – {choice.split()[0]} ({dur_label})")

    def _on_length_preset_changed(self, choice: str) -> None:
        if "Benutzerdefiniert" in choice:
            self.frame_custom_dur.pack(fill="x", padx=10, pady=(2, 4))
        else:
            self.frame_custom_dur.pack_forget()
        self._on_curve_menu_changed(self.tab2_curve_menu.get())

    def _on_tab2_playlist_changed(self) -> None:
        tracks = self._get_tab2_source_tracks()
        total_dur = sum(t.duration for t in tracks)
        self.lbl_tab2_pool_info.configure(text=f"Pool: {len(tracks)} Tracks ({format_duration(total_dur)}) verfügbar")

    def _get_tab2_source_tracks(self) -> list[Track]:
        sel = self.tab2_selected_playlist.get()
        if sel == "[ Alle Tracks ]" or sel not in self.playlists:
            return self.all_tracks
        return self.playlists.get(sel, [])

    def choose_db(self) -> None:
        f = filedialog.askopenfilename(
            title="Datenbank / XML wählen",
            filetypes=[("XML / M3U", "*.xml;*.m3u"), ("XML Dateien", "*.xml"), ("M3U Playlisten", "*.m3u"), ("Alle Dateien", "*.*")]
        )
        if f:
            self.db_path_var.set(f)

    def load_library(self) -> None:
        p_str = self.db_path_var.get().strip()
        p = Path(p_str).expanduser()
        if not p_str or not p.exists():
            messagebox.showerror(APP, "Die angegebene Datei wurde nicht gefunden. Bitte Pfad prüfen.")
            return

        is_vj = "VirtualDJ" in self.program_var.get()
        self.btn_load.configure(state="disabled", text="⏳ Lädt...")
        self.lbl_src_status.configure(text="⏳ Lade Bibliothek und Metadaten… Bitte kurz warten…")
        self.status_var.set("⏳ Lade Bibliothek…")

        def _worker():
            try:
                if is_vj:
                    files = virtualdj_playlist_candidates(p)
                    all_t, playlists = parse_virtualdj(p, files)
                else:
                    all_t, playlists = parse_rekordbox_xml(p)

                unique_t = unique_tracks(all_t)
                for t in unique_t:
                    t.energy = energy_score(t, 0)
                    if not t.camelot_key:
                        t.camelot_key = get_camelot_display(t.musical_key)

                total_sec = sum(t.duration for t in unique_t)
                msg = f"{len(unique_t)} Tracks in {len(playlists)} Playlists geladen ({format_duration(total_sec)})."

                def _finish():
                    self.all_tracks = unique_t
                    self.playlists = playlists
                    self.lbl_src_status.configure(text=msg)
                    self.status_var.set(f"Geladen: {msg}")
                    self.btn_load.configure(state="normal", text="📥 Bibliothek laden")
                    self._update_playlist_menus()
                    self._refresh_tab1_tracks()
                    self._on_tab2_playlist_changed()

                self.dispatch_to_main(_finish)

            except Exception as e:
                err_msg = str(e)
                def _error():
                    self.btn_load.configure(state="normal", text="📥 Bibliothek laden")
                    self.lbl_src_status.configure(text="Fehler beim Laden.")
                    self.status_var.set("Fehler beim Laden der Bibliothek.")
                    messagebox.showerror(APP, f"Fehler beim Laden der Bibliothek:\n{err_msg}")
                self.dispatch_to_main(_error)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_playlist_menus(self) -> None:
        names = ["[ Alle Tracks ]"] + list(self.playlists.keys())
        self.tab1_menu_playlist.configure(values=names)
        self.tab2_menu_playlist.configure(values=names)
        if self.tab1_selected_playlist.get() not in names:
            self.tab1_selected_playlist.set(names[0])
        if self.tab2_selected_playlist.get() not in names:
            self.tab2_selected_playlist.set(names[0])

    def manual_backup(self) -> None:
        p = Path(self.db_path_var.get()).expanduser()
        if not p.exists():
            messagebox.showerror(APP, "Bitte zuerst die Datenbank / XML-Datei auswählen.")
            return
        try:
            prog = "VirtualDJ" if "VirtualDJ" in self.program_var.get() else "rekordbox"
            target = backup_database(p, prog)
            now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            self.backup_state[prog] = {"time": now, "path": str(target)}
            self._save_backup_state()
            self._refresh_backup_status()
            messagebox.showinfo(APP, f"Backup erfolgreich gespeichert:\n{target}")
        except Exception as e:
            messagebox.showerror(APP, f"Backup fehlgeschlagen:\n{e}")

    # ================= TAB 1 AKTIONEN =================

    def _refresh_tab1_tracks(self) -> None:
        sel = self.tab1_selected_playlist.get()
        if sel == "[ Alle Tracks ]" or sel not in self.playlists:
            tracks = list(self.all_tracks)
        else:
            tracks = list(self.playlists.get(sel, []))

        q = self.tab1_search_var.get().strip().lower()
        if q:
            tracks = [
                t for t in tracks
                if q in t.title.lower() or q in t.artist.lower() or q in t.genre.lower()
                or q in t.musical_key.lower() or q in (t.camelot_key or "").lower()
                or q in str(round(t.bpm))
            ]

        sort_mode = self.tab1_sort_var.get()
        if "Dramaturgie" in sort_mode:
            tracks = sort_for_set(tracks, use_audio=False, exclude_incompatible=self.exclude_incompatible_var.get())
        elif "Energie aufsteigend" in sort_mode:
            tracks.sort(key=lambda x: x.energy)
        elif "Energie absteigend" in sort_mode:
            tracks.sort(key=lambda x: x.energy, reverse=True)
        elif "BPM aufsteigend" in sort_mode:
            tracks.sort(key=lambda x: (x.analyzed_bpm or x.bpm or 0))
        elif "BPM absteigend" in sort_mode:
            tracks.sort(key=lambda x: (x.analyzed_bpm or x.bpm or 0), reverse=True)
        elif "Tonart" in sort_mode:
            tracks.sort(key=lambda x: (parse_key(x.musical_key) or ("99Z", "", 99, ""))[0])
        elif "Titel" in sort_mode:
            tracks.sort(key=lambda x: (x.title or Path(x.path).stem).lower())
        elif "Interpret" in sort_mode:
            tracks.sort(key=lambda x: x.artist.lower())

        self.tab1_current_filtered = tracks

        self.tree_all.delete(*self.tree_all.get_children())
        total_sec = 0.0
        for i, t in enumerate(tracks, 1):
            dur = getattr(t, "duration", 0.0) or 210.0
            total_sec += dur
            bpm_val = f"{t.analyzed_bpm:.1f}" if getattr(t, "analyzed_bpm", 0) else (f"{t.bpm:.1f}" if t.bpm else "–")
            self.tree_all.insert(
                "", tk.END, values=(
                    f"{i:02d}",
                    t.title or Path(t.path).stem,
                    t.artist or "Unbekannt",
                    format_duration(dur),
                    bpm_val,
                    t.camelot_key or t.musical_key or "–",
                    f"{t.energy:.1f}" if t.energy else "–",
                    t.genre or "–",
                    t.path
                )
            )

        self.lbl_tab1_count.configure(text=f"{len(tracks)} Tracks · Gesamtlaufzeit: {format_duration(total_sec)}")

    def preview_tab1(self) -> None:
        tracks = getattr(self, "tab1_current_filtered", self.all_tracks)
        if not tracks:
            messagebox.showwarning(APP, "Keine Tracks zum Anzeigen vorhanden.")
            return
        p = Path(self.db_path_var.get()).expanduser() if self.db_path_var.get() else Path.home()
        outdir = (p.parent if p.is_file() else p) / "DJ Set Sorter Previews"
        outdir.mkdir(parents=True, exist_ok=True)
        name = f"Alle Tracks – {self.tab1_selected_playlist.get()}"
        safe = re.sub(r"[^A-Za-z0-9äöüÄÖÜß _-]", "_", name).strip()
        out = outdir / f"{safe}_preview.html"
        write_preview_html(tracks, name, out)
        webbrowser.open(out.as_uri())
        self.status_var.set(f"HTML-Vorschau erstellt: {out.name}")

    def export_tab1(self) -> None:
        tracks = getattr(self, "tab1_current_filtered", self.all_tracks)
        if not tracks:
            messagebox.showwarning(APP, "Keine Tracks zum Exportieren vorhanden.")
            return
        name = f"Alle Tracks ({self.tab1_selected_playlist.get()})"
        self._export_track_list(tracks, name)

    def send_tab1_to_tab2(self) -> None:
        sel = self.tab1_selected_playlist.get()
        self.tab2_selected_playlist.set(sel)
        self._on_tab2_playlist_changed()
        self.tabview.set("🎧 Neues Set (Energie-Dramaturgie)")

    # ================= TAB 2 AKTIONEN =================

    def generate_set_tab2(self) -> None:
        tracks = self._get_tab2_source_tracks()
        if not tracks:
            messagebox.showwarning(APP, "Bitte zuerst eine Playlist mit Tracks laden.")
            return

        curve_key = self.tab2_curve_key
        preset = self.tab2_length_preset.get()
        use_audio = self.audio_var.get()
        prefer_camelot = self.prefer_camelot_var.get()
        smooth_bpm = self.smooth_bpm_var.get()
        exclude_incomp = self.exclude_incompatible_var.get()
        custom_min_val = self.tab2_custom_min.get()

        target_min = None
        if "30 Min" in preset:
            target_min = 30.0
        elif "45 Min" in preset:
            target_min = 45.0
        elif "60 Min" in preset:
            target_min = 60.0
        elif "90 Min" in preset:
            target_min = 90.0
        elif "120 Min" in preset:
            target_min = 120.0
        elif "Benutzerdefiniert" in preset:
            try:
                target_min = float(custom_min_val.replace(",", "."))
            except ValueError:
                target_min = 60.0
        elif "Alle Tracks" in preset:
            target_min = None

        self.btn_generate.configure(state="disabled", text="⏳ Berechne Set…")
        self.status_var.set("⏳ Berechne optimales Set & harmonische Übergänge…")

        def _worker():
            try:
                ordered, info = generate_new_set(
                    tracks=tracks,
                    curve_key=curve_key,
                    target_minutes=target_min,
                    tolerance_minutes=5.0,
                    use_audio=use_audio,
                    prefer_camelot=prefer_camelot,
                    smooth_bpm=smooth_bpm,
                    exclude_incompatible=exclude_incomp
                )

                def _finish():
                    self.current_set_tracks = ordered
                    self.current_set_info = info

                    self.tree_set.delete(*self.tree_set.get_children())
                    prev = None
                    for i, t in enumerate(ordered, 1):
                        dur_str = format_duration(t.duration)
                        bpm_val = f"{t.analyzed_bpm:.1f}" if getattr(t, "analyzed_bpm", 0) else (f"{t.bpm:.1f}" if t.bpm else "–")
                        score, harm_label = key_transition_label(prev, t)

                        phase = t.phase or "Set"
                        tag = "phase_peak" if "Peak" in phase else "phase_build" if "Aufbau" in phase else "phase_warmup" if "Warm" in phase else "phase_cooldown"

                        self.tree_set.insert(
                            "", tk.END, values=(
                                f"{i:02d}",
                                phase,
                                t.title or Path(t.path).stem,
                                t.artist or "Unbekannt",
                                dur_str,
                                bpm_val,
                                t.camelot_key or t.musical_key or "–",
                                harm_label,
                                f"{t.energy:.1f}",
                                t.genre or "–"
                            ),
                            tags=(tag,)
                        )
                        prev = t

                    total_dur_str = info.get("formatted_duration", "–")
                    diff_sec = info.get("diff_sec", 0.0)
                    diff_str = f" (Abweichung: {diff_sec:+.0f}s)" if target_min else ""

                    self.lbl_set_title.configure(
                        text=f"✅ Set erfolgreich generiert: {len(ordered)} Tracks · Gesamtdauer: {total_dur_str}{diff_str}"
                    )

                    bpms = [t.analyzed_bpm or t.bpm for t in ordered if (t.analyzed_bpm or t.bpm)]
                    avg_bpm = f"{sum(bpms) / len(bpms):.1f}" if bpms else "–"
                    energies = [t.energy for t in ordered]
                    avg_e = f"{sum(energies) / len(energies):.1f}" if energies else "–"

                    metrics_text = (
                        f"Pool: {len(ordered)} von {len(tracks)} Tracks ausgewählt · "
                        f"Ø BPM: {avg_bpm} · Ø Energie: {avg_e} · "
                        f"Dramaturgie: {info.get('curve_title', '')}"
                    )
                    self.lbl_set_stats.configure(text=metrics_text)
                    self.btn_generate.configure(state="normal", text="⚡ NEUES SET GENERIEREN")
                    self.status_var.set(f"Fertig: {len(ordered)} Tracks für Set zusammengestellt ({total_dur_str}).")

                self.dispatch_to_main(_finish)

            except Exception as e:
                err_msg = str(e)
                def _error():
                    self.btn_generate.configure(state="normal", text="⚡ NEUES SET GENERIEREN")
                    self.status_var.set("Fehler bei der Set-Berechnung.")
                    messagebox.showerror(APP, f"Fehler bei der Set-Berechnung:\n{err_msg}")
                self.dispatch_to_main(_error)

        threading.Thread(target=_worker, daemon=True).start()

    def preview_tab2(self) -> None:
        if not self.current_set_tracks:
            messagebox.showwarning(APP, "Bitte zuerst auf 'NEUES SET GENERIEREN' klicken.")
            return
        p = Path(self.db_path_var.get()).expanduser() if self.db_path_var.get() else Path.home()
        outdir = (p.parent if p.is_file() else p) / "DJ Set Sorter Previews"
        outdir.mkdir(parents=True, exist_ok=True)
        name = self.tab2_set_name.get().strip() or "Neues Set"
        safe = re.sub(r"[^A-Za-z0-9äöüÄÖÜß _-]", "_", name).strip()
        out = outdir / f"{safe}_preview.html"
        write_preview_html(self.current_set_tracks, name, out, set_info=self.current_set_info)
        webbrowser.open(out.as_uri())
        self.status_var.set(f"HTML-Vorschau erstellt: {out.name}")

    def export_tab2(self) -> None:
        if not self.current_set_tracks:
            messagebox.showwarning(APP, "Bitte zuerst auf 'NEUES SET GENERIEREN' klicken.")
            return
        name = self.tab2_set_name.get().strip() or "Neues Set"
        self._export_track_list(self.current_set_tracks, name)

    def copy_set_to_clipboard(self) -> None:
        if not self.current_set_tracks:
            messagebox.showwarning(APP, "Keine Tracks im Set vorhanden.")
            return
        lines = [f"{i:02d}. {t.artist} – {t.title} [{format_duration(t.duration)} | {t.bpm:.0f} BPM | {t.camelot_key}]" for i, t in enumerate(self.current_set_tracks, 1)]
        text = f"DJ Set: {self.tab2_set_name.get()}\n" + "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo(APP, f"Trackliste mit {len(self.current_set_tracks)} Tracks in die Zwischenablage kopiert!")

    def _export_track_list(self, tracks: list[Track], name: str) -> None:
        p = Path(self.db_path_var.get()).expanduser()
        if not p.exists():
            messagebox.showerror(APP, "Datenbank-Pfad ungültig.")
            return

        try:
            prog = "VirtualDJ" if "VirtualDJ" in self.program_var.get() else "rekordbox"
            backup = backup_database(p, prog) if self.backup_var.get() else None
            if backup:
                now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
                self.backup_state[prog] = {"time": now, "path": str(backup)}
                self._save_backup_state()
                self._refresh_backup_status()

            outdir = (p.parent if p.is_file() else p) / "DJ Set Sorter Playlists"
            outdir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9äöüÄÖÜß _-]", "_", name).strip() or "Set"

            if "VirtualDJ" in self.program_var.get():
                out = outdir / f"{safe}.m3u"
                write_virtualdj_m3u(tracks, out)
            else:
                out = outdir / f"{safe}.xml"
                write_rekordbox_xml(tracks, name, out)

            total_dur = sum(t.duration for t in tracks)
            msg = f"Playlist erfolgreich erstellt:\n{out}\n\nTracks: {len(tracks)} · Gesamtdauer: {format_duration(total_dur)}"
            if backup:
                msg += f"\n\nSicherheits-Backup gespeichert unter:\n{backup}"
            messagebox.showinfo(APP, msg)
            self.status_var.set(f"Exportiert: {out.name} ({len(tracks)} Tracks)")

        except Exception as e:
            messagebox.showerror(APP, f"Fehler beim Exportieren:\n{e}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
