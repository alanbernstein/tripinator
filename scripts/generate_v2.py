#!/usr/bin/env python3
"""
tripinator v2 - scrollytelling trip report generator

Usage: python generate_v2.py <trip_dir> "<title>"

Expects:
  <trip_dir>/img/         - JPEG photos (Pixel PXL_* naming)
  <trip_dir>/tracks/      - GPX track files (optional)
  <trip_dir>/captions.json - {"filename.jpg": "caption text"} (optional)

Outputs:
  <trip_dir>/img-thumb/   - generated thumbnails (1200px max width)
  <trip_dir>/index.html   - the trip report
"""

import os
import re
import sys
import json
import datetime
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader

THUMB_MAX_PX = 1200


# ── EXIF ──────────────────────────────────────────────────────────────────────

def get_all_exif(img_dir):
    """Batch-read EXIF for all JPEGs in a directory via exiftool -json."""
    result = subprocess.check_output(
        ['exiftool', '-json', str(img_dir)], text=True)
    data = json.loads(result)
    return {os.path.basename(item['SourceFile']): item for item in data}


def dms_to_dd(dms_str):
    """Convert '47 deg 37\\' 38.64\\" N' to decimal degrees."""
    nums = re.findall(r'[0-9.]+', dms_str)
    d, m, s = int(nums[0]), int(nums[1]), float(nums[2])
    dd = d + m / 60 + s / 3600
    if dms_str.strip()[-1] in 'SW':
        dd = -dd
    return dd


def parse_local_dt(exif):
    """Return aware datetime in local tz from SubSecCreateDate or CreateDate+OffsetTime."""
    val = exif.get('SubSecCreateDate') or exif.get('SubSecDateTimeOriginal', '')
    if not val:
        val = exif.get('CreateDate', '')
        offset_str = exif.get('OffsetTime', '')
        if offset_str:
            val = val + offset_str

    m = re.match(r'(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})', val)
    if not m:
        return None
    Y, Mo, D, h, mi, s = [int(x) for x in m.groups()]
    tz_m = re.search(r'([+-])(\d{2}):(\d{2})', val)
    if tz_m:
        sign = 1 if tz_m.group(1) == '+' else -1
        offset = datetime.timedelta(
            hours=sign * int(tz_m.group(2)),
            minutes=sign * int(tz_m.group(3)))
        tz = datetime.timezone(offset)
        return datetime.datetime(Y, Mo, D, h, mi, s, tzinfo=tz)
    return datetime.datetime(Y, Mo, D, h, mi, s)


def parse_exif_gps(exif):
    """Return (lat, lon, ele_m) from EXIF or (None, None, None)."""
    if 'GPSLatitude' not in exif or 'GPSLongitude' not in exif:
        return None, None, None
    lat = dms_to_dd(exif['GPSLatitude'])
    lon = dms_to_dd(exif['GPSLongitude'])
    ele_m = None
    alt = exif.get('GPSAltitude', '')
    m = re.findall(r'[0-9.]+', alt)
    if m:
        ele_m = float(m[0])
        if 'Below' in alt:
            ele_m = -ele_m
    return lat, lon, ele_m


# ── GPX ───────────────────────────────────────────────────────────────────────

def parse_gpx(fname):
    """Parse GPX → list of dicts with time (aware UTC), lat, lon, ele."""
    tree = ET.parse(fname)
    root = tree.getroot()
    ns = {'g': 'http://www.topografix.com/GPX/1/1'}
    points = []
    for trkpt in root.findall('.//g:trkpt', ns):
        lat = float(trkpt.get('lat'))
        lon = float(trkpt.get('lon'))
        ele_el = trkpt.find('g:ele', ns)
        ele = float(ele_el.text) if ele_el is not None else 0.0
        time_el = trkpt.find('g:time', ns)
        if time_el is not None:
            ts = datetime.datetime.fromisoformat(
                time_el.text.replace('Z', '+00:00'))
            points.append({'time': ts, 'lat': lat, 'lon': lon, 'ele': ele})
    return points


def interpolate_position(dt_utc, trackpoints):
    """Linearly interpolate lat/lon/ele at dt_utc from sorted trackpoints."""
    if not trackpoints:
        return None, None, None
    before = after = None
    for tp in trackpoints:
        if tp['time'] <= dt_utc:
            before = tp
        else:
            after = tp
            break
    if before is None:
        return after['lat'], after['lon'], after['ele']
    if after is None:
        return before['lat'], before['lon'], before['ele']
    total = (after['time'] - before['time']).total_seconds()
    frac = (dt_utc - before['time']).total_seconds() / total if total > 0 else 0
    return (
        before['lat'] + frac * (after['lat'] - before['lat']),
        before['lon'] + frac * (after['lon'] - before['lon']),
        before['ele'] + frac * (after['ele'] - before['ele']),
    )


def parse_pxl_utc(fname):
    """Parse UTC datetime from PXL_YYYYMMDD_HHMMSSsss filename."""
    m = re.search(r'PXL_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', fname)
    if m:
        Y, Mo, D, h, mi, s = [int(x) for x in m.groups()]
        return datetime.datetime(Y, Mo, D, h, mi, s,
                                  tzinfo=datetime.timezone.utc)
    return None


# ── THUMBNAILS & POSTERS ─────────────────────────────────────────────────────

def make_thumbnail(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run(
        ['convert', str(src), '-resize', f'{THUMB_MAX_PX}x{THUMB_MAX_PX}>',
         '-quality', '82', str(dst)],
        check=True)


def make_video_poster(video_path, poster_path, seek='2'):
    """Extract a single frame from a video for use as poster image."""
    os.makedirs(os.path.dirname(poster_path), exist_ok=True)
    result = subprocess.run(
        ['ffmpeg', '-y', '-ss', seek, '-i', str(video_path),
         '-vframes', '1', '-q:v', '3', str(poster_path)],
        capture_output=True)
    if result.returncode != 0:
        # Some clips are shorter than the seek point — try the start
        subprocess.run(
            ['ffmpeg', '-y', '-i', str(video_path),
             '-vframes', '1', '-q:v', '3', str(poster_path)],
            check=True, capture_output=True)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    trip_dir = Path(sys.argv[1]).resolve()
    title = sys.argv[2] if len(sys.argv) > 2 else trip_dir.name.replace('-', ' ').title()
    script_dir = Path(__file__).parent

    print(f'Trip dir: {trip_dir}')
    print(f'Title: {title}')

    # ── Load GPX tracks ──────────────────────────────────────────────────────
    all_trackpoints = []   # merged, sorted by time
    track_features = []    # GeoJSON features for the map
    tracks_dir = trip_dir / 'tracks'

    track_time_ranges = []  # (start_utc, end_utc, track_index)

    if tracks_dir.exists():
        for track_i, gpx_file in enumerate(sorted(tracks_dir.glob('*.gpx'))):
            print(f'  track: {gpx_file.name}')
            tps = parse_gpx(gpx_file)
            if not tps:
                continue
            track_time_ranges.append((tps[0]['time'], tps[-1]['time'], track_i))
            all_trackpoints.extend(tps)
            coords = [[tp['lon'], tp['lat'], round(tp['ele'], 1)] for tp in tps]
            track_features.append({
                'type': 'Feature',
                'geometry': {'type': 'LineString', 'coordinates': coords},
                'properties': {'name': gpx_file.stem},
            })

    all_trackpoints.sort(key=lambda x: x['time'])

    # ── Load metadata (captions + tags) ─────────────────────────────────────
    metadata = {}
    metadata_file = trip_dir / 'metadata.json'
    captions_file = trip_dir / 'captions.json'
    if metadata_file.exists():
        with open(metadata_file) as f:
            raw = json.load(f)
        # Normalise: values might be plain strings (old captions.json format)
        for k, v in raw.items():
            metadata[k] = v if isinstance(v, dict) else {'caption': v, 'tags': []}
        print(f'  metadata: {len(metadata)} entries')
    elif captions_file.exists():
        with open(captions_file) as f:
            raw = json.load(f)
        metadata = {k: {'caption': v, 'tags': []} for k, v in raw.items()}
        print(f'  captions (legacy): {len(metadata)} entries')

    # ── Load photos ──────────────────────────────────────────────────────────
    img_dir = trip_dir / 'img'
    thumb_dir = trip_dir / 'img-thumb'

    print('Reading EXIF...')
    all_exif = get_all_exif(img_dir)

    items = []
    for img_file in sorted(img_dir.glob('*.jpg')):
        exif = all_exif.get(img_file.name, {})

        # Timestamp
        local_dt = parse_local_dt(exif)
        dt_utc = parse_pxl_utc(img_file.name)

        if local_dt is None and dt_utc is not None:
            # No timezone in EXIF - assume Pacific (UTC-8)
            tz = datetime.timezone(datetime.timedelta(hours=-8))
            local_dt = dt_utc.astimezone(tz)

        # GPS
        lat, lon, ele_m = parse_exif_gps(exif)

        # Interpolate from track if no embedded GPS
        if lat is None and dt_utc is not None and all_trackpoints:
            lat, lon, ele_m = interpolate_position(dt_utc, all_trackpoints)
            gps_source = 'track'
        else:
            gps_source = 'exif'

        # Image dimensions
        try:
            w = int(exif.get('ExifImageWidth') or exif.get('ImageWidth', 4080))
            h = int(exif.get('ExifImageHeight') or exif.get('ImageHeight', 3072))
        except (ValueError, TypeError):
            w, h = 4080, 3072

        # Thumbnail
        thumb_path = thumb_dir / img_file.name
        if not thumb_path.exists():
            print(f'  thumbnail: {img_file.name}')
            make_thumbnail(img_file, thumb_path)

        item = {
            'type': 'image',
            'filename': img_file.name,
            'poster': None,
            'dt_utc': dt_utc,
            'local_dt': local_dt,
            'date': local_dt.date() if local_dt else None,
            'time_str': local_dt.strftime('%-I:%M %p') if local_dt else '',
            'lat': round(lat, 6) if lat is not None else None,
            'lon': round(lon, 6) if lon is not None else None,
            'ele_m': round(ele_m, 1) if ele_m is not None else None,
            'ele_ft': round(ele_m * 3.28084) if ele_m is not None else None,
            'aspect': round(w / h, 3) if h else 1.333,
            'is_portrait': (w < h),
            'is_pano': (w > h * 2.2),
            'caption': metadata.get(img_file.name, {}).get('caption') or None,
            'tags': metadata.get(img_file.name, {}).get('tags', []),
            'gps_source': gps_source,
            'track_idx': next(
                (idx for start, end, idx in track_time_ranges
                 if dt_utc and start <= dt_utc <= end),
                -1),
        }
        items.append(item)

    print(f'  {len(items)} photos loaded')

    # ── Load videos ──────────────────────────────────────────────────────────
    video_dir   = trip_dir / 'video'
    poster_dir  = trip_dir / 'video-poster'

    if video_dir.exists():
        vid_files = sorted(video_dir.glob('*.mp4'))
        if vid_files:
            print('Reading video EXIF...')
            vid_exif = get_all_exif(video_dir)

            for vid_file in vid_files:
                exif = vid_exif.get(vid_file.name, {})

                dt_utc = parse_pxl_utc(vid_file.name)
                local_dt = None
                if dt_utc is not None:
                    tz = datetime.timezone(datetime.timedelta(hours=-8))
                    local_dt = dt_utc.astimezone(tz)

                lat, lon, ele_m = parse_exif_gps(exif)
                if lat is None and dt_utc is not None and all_trackpoints:
                    lat, lon, ele_m = interpolate_position(dt_utc, all_trackpoints)

                try:
                    w = int(exif.get('ImageWidth', 1920))
                    h = int(exif.get('ImageHeight', 1080))
                    rotation = int(exif.get('Rotation', 0))
                    if rotation in (90, 270):
                        w, h = h, w
                except (ValueError, TypeError):
                    w, h = 1920, 1080

                poster_name = vid_file.stem + '.jpg'
                poster_path = poster_dir / poster_name
                if not poster_path.exists():
                    print(f'  poster: {vid_file.name}')
                    try:
                        make_video_poster(vid_file, poster_path)
                    except Exception as e:
                        print(f'    skipping (ffmpeg error): {e}')
                        continue

                item = {
                    'type': 'video',
                    'filename': vid_file.name,
                    'poster': poster_name,
                    'dt_utc': dt_utc,
                    'local_dt': local_dt,
                    'date': local_dt.date() if local_dt else None,
                    'time_str': local_dt.strftime('%-I:%M %p') if local_dt else '',
                    'lat': round(lat, 6) if lat is not None else None,
                    'lon': round(lon, 6) if lon is not None else None,
                    'ele_m': round(ele_m, 1) if ele_m is not None else None,
                    'ele_ft': round(ele_m * 3.28084) if ele_m is not None else None,
                    'aspect': round(w / h, 3) if h else 1.777,
                    'is_portrait': (w < h),
                    'is_pano': False,
                    'caption': metadata.get(vid_file.name, {}).get('caption') or None,
                    'tags': metadata.get(vid_file.name, {}).get('tags', []),
                    'track_idx': next(
                        (idx for start, end, idx in track_time_ranges
                         if dt_utc and start <= dt_utc <= end),
                        -1),
                }
                items.append(item)

            print(f'  {sum(1 for i in items if i["type"] == "video")} videos loaded')

    # ── Sort by timestamp and assign IDs ─────────────────────────────────────
    items.sort(key=lambda x: x['dt_utc'] or datetime.datetime.min.replace(
        tzinfo=datetime.timezone.utc))
    for i, item in enumerate(items):
        item['id'] = i

    # ── Group by local date ──────────────────────────────────────────────────
    days_dict = defaultdict(list)
    for item in items:
        days_dict[item['date']].append(item)

    days = []
    for date in sorted(days_dict.keys()):
        day_items = days_dict[date]
        label = date.strftime('%A, %B %-d') if date else 'Unknown'
        days.append({'date': date, 'label': label, 'photos': day_items})

    # ── JS data for frontend ─────────────────────────────────────────────────
    js_items = [{
        'id': item['id'],
        'type': item['type'],
        'filename': item['filename'],
        'poster': item['poster'],
        'lat': item['lat'],
        'lon': item['lon'],
        'caption': item['caption'] or '',
        'tags': item.get('tags', []),
        'time': item['time_str'],
        'ele_ft': item['ele_ft'],
        'track_idx': item['track_idx'],
    } for item in items]

    # ── Collect unique tags ──────────────────────────────────────────────────
    all_tags = sorted(set(tag for item in items for tag in item.get('tags', [])))

    # Compute map center from track or photo midpoint
    lats = [i['lat'] for i in items if i['lat'] is not None]
    lons = [i['lon'] for i in items if i['lon'] is not None]
    if lats:
        map_center = [
            round((min(lats) + max(lats)) / 2, 5),
            round((min(lons) + max(lons)) / 2, 5),
        ]
    else:
        map_center = [47.6, -122.3]

    # ── Render template ──────────────────────────────────────────────────────
    env = Environment(loader=FileSystemLoader(str(script_dir)))
    tmpl = env.get_template('template_v2.html')

    html = tmpl.render(
        title=title,
        days=days,
        item_count=len(items),
        tracks_json=json.dumps(track_features),
        items_json=json.dumps(js_items),
        map_center=json.dumps(map_center),
        all_tags_json=json.dumps(all_tags),
    )

    output = trip_dir / 'index.html'
    output.write_text(html)
    print(f'\nGenerated: {output}')


if __name__ == '__main__':
    main()
