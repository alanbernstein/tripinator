import datetime
import json
import glob
import os
import re

import jinja2
import json

from exif import get_exif_tags, get_details


from debug import pm, debug, pp

# run this inside the `my-trip` directory

# TODO: figure out thumbnail and poster filenames automatically, by checking the basename without the extension


@pm
def main():
    metadata = []
    base_md = {
        'caption': '',
        'tags': [],
        'rating': 5,
    }

    for n, f in enumerate(glob.glob('img/*')):
        md = {'filename': f, 'basename': os.path.basename(f)}
        md.update(base_md)
        exif = get_exif_tags(f)
        details = get_details(f, exif)
        if 'error' in details:
            print('%3d. %s: %s' % (n, f, details['error']))
            if 'error' in details:
                continue
            if details['error'] == 'unknown format':
                continue
            md['rating'] = 1
        else:
            print('%3d. %s' % (n, f))

        md.update(details)
        for k, v in md.items():
            print('  %s: %s' % (k, v))
            pass
        metadata.append(md)

    metadata.sort(key=lambda x: x['ts'])

    generate_html(metadata, 'maternity 2020', 'template-simple-dslr.html', 'index.html')
    # metadata_images_gps = [x for x in metadata if 'lat' in x]
    # generate_html(metadata_images_gps, 'pecos 2020', 'template-trip-full.html', 'index.html')



# given:
# - metadata json file produced by generate_metadata.py,
# - title string
# - template file
#
# this should generate a complete html file, which can then
# be copied into the appropriate trip directory (e.g. sample-trip)
# and it will work as expected as long as all media and other assets
# are present in the correct locations


def generate_html(metadata, title, template_file, output_file):
    templateLoader = jinja2.FileSystemLoader(searchpath="../scripts/")
    templateEnv = jinja2.Environment(loader=templateLoader)
    template = templateEnv.get_template(template_file)
    rendered = template.render(metadata=metadata, title=title)

    with open(output_file, 'w') as f:
        f.write(rendered)

    print('wrote %d bytes to %s' % (len(rendered), output_file))


main()
