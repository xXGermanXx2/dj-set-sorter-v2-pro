import tempfile
from pathlib import Path
from dj_set_sorter import (
    Track, sort_for_set, write_rekordbox_xml, parse_rekordbox_xml,
    generate_new_set, parse_key, key_compatibility, key_transition_label,
    CURVE_PROFILES
)


def test_sort_increases_energy():
    tracks = [Track(path=f"/x/{i}.mp3", title=str(i), genre=g, bpm=b) for i, (g, b) in enumerate([
        ("ambient", 90), ("house", 120), ("hard techno", 145), ("deep house", 110), ("techno", 135)])]
    result = sort_for_set(tracks)
    assert result[0].energy <= result[1].energy
    assert result[-1].energy >= result[0].energy


def test_rekordbox_roundtrip():
    tracks = [Track(path="/music/a.mp3", title="A", artist="DJ", bpm=128, duration=240.0, musical_key="8A")]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "out.xml"
        write_rekordbox_xml(tracks, "Test Set", p)
        all_tracks, playlists = parse_rekordbox_xml(p)
        assert len(all_tracks) == 1
        assert "Test Set" in playlists
        assert playlists["Test Set"][0].title == "A"
        assert playlists["Test Set"][0].duration == 240.0


def test_camelot_key_parsing():
    assert parse_key("8A") == ("8A", "Am", 9, "A")
    assert parse_key("08A") == ("8A", "Am", 9, "A")
    assert parse_key("Am") == ("8A", "Am", 9, "A")
    assert parse_key("A minor") == ("8A", "Am", 9, "A")
    assert parse_key("C") == ("8B", "C", 0, "B")
    assert parse_key("11B") == ("11B", "A", 9, "B")


def test_camelot_compatibility():
    t_8a = Track(path="/x/1.mp3", musical_key="8A")
    t_8a_same = Track(path="/x/2.mp3", musical_key="Am")
    t_8b_rel = Track(path="/x/3.mp3", musical_key="C")
    t_9a_adj = Track(path="/x/4.mp3", musical_key="9A")
    t_2a_far = Track(path="/x/5.mp3", musical_key="2A")

    assert key_compatibility(t_8a, t_8a_same) == 100.0
    assert key_compatibility(t_8a, t_8b_rel) == 95.0
    assert key_compatibility(t_8a, t_9a_adj) == 90.0
    assert key_compatibility(t_8a, t_2a_far) <= 45.0


def test_generate_new_set_duration_constraint():
    # 30 tracks with ~240s duration each (~120 minutes total)
    pool = [
        Track(path=f"/music/{i}.mp3", title=f"Track {i}", bpm=124 + (i % 6),
              duration=240.0, genre="house" if i % 2 == 0 else "techno")
        for i in range(30)
    ]
    # Request a 60-minute set with +/- 5 min tolerance
    ordered, info = generate_new_set(pool, curve_key="classic_peak", target_minutes=60.0, tolerance_minutes=5.0)

    # Must select a subset (not all 30 tracks)
    assert len(ordered) < len(pool)
    assert 12 <= len(ordered) <= 18
    # Total duration should be close to 60 min (3600s +/- 360s)
    total_dur = sum(t.duration for t in ordered)
    assert 3200 <= total_dur <= 4000
    assert info["track_count"] == len(ordered)


def test_generate_new_set_curves():
    # Verify every defined curve runs without error
    pool = [
        Track(path=f"/music/{i}.mp3", title=f"Track {i}", bpm=120 + i,
              duration=210.0, genre="techno")
        for i in range(20)
    ]
    for curve_name in CURVE_PROFILES:
        ordered, info = generate_new_set(pool, curve_key=curve_name, target_minutes=30.0)
        assert len(ordered) > 0
        assert all(t.phase != "" for t in ordered)


def test_all_tracks_mode_uses_all_tracks():
    pool = [Track(path=f"/music/{i}.mp3", title=f"T{i}", duration=200.0) for i in range(15)]
    # target_minutes=None or 0 means all tracks are used
    ordered, info = generate_new_set(pool, curve_key="linear_rise", target_minutes=None)
    assert len(ordered) == len(pool)


if __name__ == "__main__":
    test_sort_increases_energy()
    test_rekordbox_roundtrip()
    test_camelot_key_parsing()
    test_camelot_compatibility()
    test_generate_new_set_duration_constraint()
    test_generate_new_set_curves()
    test_all_tracks_mode_uses_all_tracks()
    print("All unit tests passed successfully!")
