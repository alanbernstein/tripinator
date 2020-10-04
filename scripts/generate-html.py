import jinja2
import json

# given:
# - metadata json file produced by generate_metadata.py,
# - title string
# - template file
#
# this should generate a complete html file, which can then
# be copied into the appropriate trip directory (e.g. sample-trip)
# and it will work as expected as long as all media and other assets
# are present in the correct locations

TEMPLATE_FILE = "trip-full-template.html"
output_file = 'trip.html'


def main():
    title = 'pecos wilderness 2020'
    with open('sample-metadata.json') as f:
        metadata = json.load(f)

    metadata_images_gps = [x for x in metadata if 'lat' in x]

    templateLoader = jinja2.FileSystemLoader(searchpath="./")
    templateEnv = jinja2.Environment(loader=templateLoader)
    template = templateEnv.get_template(TEMPLATE_FILE)
    rendered = template.render(metadata=metadata_images_gps, title=title)

    with open(output_file, 'w') as f:
        f.write(rendered)

    print('wrote %d bytes to %s' % (len(rendered), output_file))


main()
