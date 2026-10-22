"""Compose approved CAD outlines once, after surface denoising.

Input geometry is per-frame pixel coordinates, not a reusable static video layer.
Does not alter the source render or source JSON. Pillow runs in system Python.
"""
from pathlib import Path
import argparse
import json
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / '02_studio/presets/module_outline_approved.json'


def compose(faces, edges, output, profile=DEFAULT_PROFILE):
    style_config = json.loads(Path(profile).read_text(encoding='utf-8'))
    style = style_config['style']
    settings = style_config['edge_selection']
    data = json.loads(Path(edges).read_text(encoding='utf-8'))
    base = Image.open(faces).convert('RGB')
    width = float(style['edge_width_px'])
    if style['scale_edge_width_with_output_height']:
        width *= base.height / float(style['reference_height_px'])
    scale = int(settings['antialias_supersampling'])
    mask = Image.new('L', (base.width * scale, base.height * scale), 0)
    draw = ImageDraw.Draw(mask)
    for segment in data['lines']:
        draw.line([(x * scale, y * scale) for x, y in segment],
                  fill=255, width=max(1, round(width * scale)))
    mask = mask.resize(base.size, Image.Resampling.LANCZOS)
    mask = mask.point(lambda value: round(value * style['edge_opacity']))
    base.paste(Image.new('RGB', base.size, style['edge_color_srgb_hex']), (0, 0), mask)
    output = Path(output)
    if output.resolve() in (Path(faces).resolve(), Path(edges).resolve(), Path(profile).resolve()):
        raise ValueError('Output must not replace an input or the approved profile')
    output.parent.mkdir(parents=True, exist_ok=True)
    base.save(output, optimize=True)
    return {'profile_id': style_config['profile_id'], 'output_size': list(base.size),
            'edge_width_px': width, 'edge_opacity': style['edge_opacity'],
            'edge_color': style['edge_color_srgb_hex'], 'segments': len(data['lines'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--faces', required=True)
    parser.add_argument('--edges', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--profile', default=str(DEFAULT_PROFILE))
    args = parser.parse_args()
    print(json.dumps(compose(args.faces, args.edges, args.output, args.profile)))


if __name__ == '__main__':
    main()
