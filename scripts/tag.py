#!/usr/bin/env python3
"""
tag.py - CLI tool for adding captions and tags to trip media

Usage:
  python tag.py <trip_dir>           # tag untagged items only
  python tag.py <trip_dir> --all     # include already-tagged items
  python tag.py <trip_dir> --display chafa   # force a display method

Saves/updates <trip_dir>/metadata.json:
  { "filename.jpg": { "caption": "...", "tags": ["tag1", "tag2"] }, ... }

Commands at each prompt:
  Enter        keep/skip (no change)
  any text     set the value
  [caption prompt] type 's' alone to skip this item entirely
  Ctrl-C / q   quit and save progress
"""

import os
import sys
import json
import shutil
import readline
import subprocess
from pathlib import Path


# ── Image display ─────────────────────────────────────────────────────────────

DISPLAY_METHODS = ['wezterm', 'imgcat', 'kitty', 'viu', 'timg', 'chafa']

def detect_display():
    term_program = os.environ.get('TERM_PROGRAM', '')
    term         = os.environ.get('TERM', '')

    # WezTerm: use its built-in imgcat subcommand (iTerm2 protocol)
    if term_program == 'WezTerm' or shutil.which('wezterm'):
        if shutil.which('wezterm'):
            return 'wezterm'
    # iTerm2 or other terminals with a standalone imgcat binary
    if shutil.which('imgcat'):
        return 'imgcat'
    # Kitty terminal: built-in icat kitten
    if term == 'xterm-kitty' and shutil.which('kitty'):
        return 'kitty'
    # viu: Kitty protocol in Kitty, sixel elsewhere
    if shutil.which('viu'):
        return 'viu'
    # timg: auto-detects iTerm2/WezTerm/sixel based on TERM_PROGRAM
    if shutil.which('timg'):
        return 'timg'
    # chafa: unicode block art, works in any terminal
    if shutil.which('chafa'):
        return 'chafa'
    return None

def make_show_fn(method):
    """Return a callable that displays an image file."""
    if method == 'wezterm':
        return lambda p: subprocess.run(['wezterm', 'imgcat', '--height', '30', str(p)])
    if method == 'imgcat':
        return lambda p: subprocess.run(['imgcat', str(p)])
    if method == 'kitty':
        return lambda p: subprocess.run(['kitty', '+kitten', 'icat',
                                         '--scale-up', '--place', '80x30@0x0', str(p)])
    if method == 'viu':
        return lambda p: subprocess.run(['viu', '-w', '80', '-h', '30', str(p)])
    if method == 'timg':
        return lambda p: subprocess.run(['timg', '-g', '80x30', str(p)])
    if method == 'chafa':
        return lambda p: subprocess.run(['chafa', '--size', '80x30', str(p)])
    return None


# ── Metadata I/O ──────────────────────────────────────────────────────────────

def load_metadata(path):
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        # Normalise: values might be plain strings (old captions.json format)
        for k, v in data.items():
            if isinstance(v, str):
                data[k] = {'caption': v, 'tags': []}
        return data
    return {}

def save_metadata(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


# ── Readline prompts with pre-filled defaults ─────────────────────────────────

def prompt(label, default=''):
    """Prompt with default pre-filled; user can edit in place."""
    def hook():
        readline.insert_text(default)
        readline.redisplay()
    readline.set_pre_input_hook(hook)
    try:
        result = input(f'  {label}: ')
    except (EOFError, KeyboardInterrupt):
        raise KeyboardInterrupt
    finally:
        readline.set_pre_input_hook(None)
    return result.strip()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Add captions/tags to trip media')
    parser.add_argument('trip_dir')
    parser.add_argument('--all', action='store_true',
                        help='Include already-tagged items (default: skip them)')
    parser.add_argument('--display', choices=DISPLAY_METHODS + ['none'],
                        help='Force image display method')
    args = parser.parse_args()

    trip_dir = Path(args.trip_dir).resolve()
    if not trip_dir.is_dir():
        sys.exit(f'Not a directory: {trip_dir}')

    metadata_path = trip_dir / 'metadata.json'

    # Prefer metadata.json, fall back to captions.json for import
    if not metadata_path.exists() and (trip_dir / 'captions.json').exists():
        print('Importing existing captions.json → metadata.json')
        metadata = load_metadata(trip_dir / 'captions.json')
    else:
        metadata = load_metadata(metadata_path)

    # Display setup
    if args.display == 'none':
        show = None
        print('Image display disabled.')
    else:
        method = args.display or detect_display()
        show = make_show_fn(method) if method else None
        if show:
            print(f'Display: {method}')
        else:
            print('No image display found (install chafa or viu for terminal previews).')

    # Collect items: photos first, then video posters
    items = []  # (key, preview_path, label)
    img_dir = trip_dir / 'img'
    if img_dir.exists():
        for f in sorted(img_dir.glob('*.jpg')):
            items.append((f.name, f, f.name))

    video_dir   = trip_dir / 'video'
    poster_dir  = trip_dir / 'video-poster'
    if video_dir.exists():
        for f in sorted(video_dir.glob('*.mp4')):
            poster = poster_dir / (f.stem + '.jpg')
            preview = poster if poster.exists() else None
            items.append((f.name, preview, f'[video] {f.name}'))

    # Filter to untagged unless --all
    if not args.all:
        untagged = [(k, p, l) for k, p, l in items
                    if not metadata.get(k, {}).get('caption')
                    and not metadata.get(k, {}).get('tags')]
        print(f'{len(items)} total items, {len(untagged)} untagged\n')
        items = untagged
    else:
        print(f'{len(items)} items\n')

    if not items:
        print('Nothing to tag. Use --all to re-tag existing items.')
        return

    print('Enter caption and tags at each prompt (pre-filled with current values).')
    print('  s  at caption prompt = skip this item')
    print('  q  at caption prompt = quit\n')

    updated = 0
    for i, (key, preview_path, label) in enumerate(items):
        # Divider
        print(f'\n{"─" * 60}')
        print(f'  {i+1}/{len(items)}  {label}')
        print()

        current = metadata.get(key, {})
        current_caption = current.get('caption', '')
        current_tags    = ', '.join(current.get('tags', []))

        # Show image
        if show and preview_path and preview_path.exists():
            show(preview_path)
            print()

        # Prompts
        try:
            caption = prompt('Caption', current_caption)
        except KeyboardInterrupt:
            print('\nQuitting.')
            break

        if caption.lower() == 'q':
            print('Quitting.')
            break
        if caption.lower() == 's':
            print('  skipped.')
            continue

        try:
            tags_raw = prompt('Tags (comma-separated)', current_tags)
        except KeyboardInterrupt:
            # Save caption already entered, then quit
            tags_raw = current_tags
            save_metadata(metadata_path, metadata)
            print('\nQuitting.')
            break

        tags = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else []

        new_entry = {'caption': caption, 'tags': tags}
        if new_entry != current:
            metadata[key] = new_entry
            save_metadata(metadata_path, metadata)
            updated += 1
            print(f'  saved.')
        else:
            print(f'  no change.')

    print(f'\n{updated} items updated → {metadata_path}')


if __name__ == '__main__':
    main()
