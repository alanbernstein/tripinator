import jinja2
import json


TEMPLATE_FILE = "trip-template.html"
output_file = 'trip.html'


def main():
    with open('metadata-v3-with-comments.json') as f:
        metadata = json.load(f)

    metadata_videos = [x for x in metadata if x['filename'].endswith('.mp4')]
    metadata_images = [x for x in metadata if x['filename'].endswith('.jpg')]
    metadata_images_gps = [x for x in metadata if 'lat' in x]

    templateLoader = jinja2.FileSystemLoader(searchpath="./")
    templateEnv = jinja2.Environment(loader=templateLoader)
    template = templateEnv.get_template(TEMPLATE_FILE)
    rendered = template.render(metadata=metadata_images_gps, videos=[])

    with open(output_file, 'w') as f:
        f.write(rendered)

    print('wrote %d bytes to %s' % (len(rendered), output_file))


main()
