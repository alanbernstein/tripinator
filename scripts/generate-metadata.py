import datetime
import json
import glob
import os
import re
import subprocess

from panda.debug import pm, debug, pp


m2ft = 100./2.54/12

# TODO: put thumbnail filename in metadata explicitly

@pm
def main():
    metadata = []
    base_md = {
        'caption': '',
        'tags': [],
        'rating': 5,
    }

    for n, f in enumerate(glob.glob('../pecos-2020/img/*')):
        md = {'filename': f, 'basename': os.path.basename(f)}
        md.update(base_md)
        exif = get_exif_tags(f)
        details = get_details(f, exif)
        if 'error' in details:
            print('%3d. %s: %s' % (n, f, details['error']))
            if details['error'] == 'unknown format':
                continue
            md['rating'] = 1
        else:
            print('%3d. %s' % (n, f))

        md.update(details)
        metadata.append(md)

    metadata.sort(key=lambda x: x['ts'])

    debug()
    with open('metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)


def get_details(fname, exif):
    # this function was written to handle media from specific devices, since
    # exif never seems to be consistent.
    #
    # alan's pixel 3a
    # might have file names like these:
    #   IMG_20200902_213234.jpg - normal still image
    #   MVIMG_20200902_213341.jpg - file that acts like a still image, but is actually a short video if the viewer understands that
    #   VID_20200902_193614.mp4 - normal mp4 video
    #   00000IMG_00000_BURST20200904115433782_COVER.jpg - still image that identifies and/or contains a short burst of photos
    #   VID_20200905_161348_LS.mp4 - ?
    #   PANO_20200904_115441.vr.jpg - panoramic image
    #
    # cody's iphone 8
    #   IMG_1191.jpeg
    #   IMG_1192.mov
    #
    ######################
    # timestamps
    # additionally, alan's photos were transferred via both phone->dropbox->laptop and phone->google->laptop
    # apparently at least one of these messes with the exif timestamp data:
    #
    # $ exiftool alan-google/VID_20200905_155952.mp4 | grep -i date
    # File Modification Date/Time     : 2020:09:05 21:59:52-05:00
    # File Access Date/Time           : 2020:09:24 23:50:08-05:00
    # File Inode Change Date/Time     : 2020:09:23 23:27:08-05:00
    # Create Date                     : 2020:09:05 21:59:52
    # Modify Date                     : 2020:09:08 03:48:27
    # Track Create Date               : 2020:09:08 03:48:27
    # Track Modify Date               : 2020:09:08 03:48:27
    # Media Create Date               : 2020:09:08 03:48:27
    # Media Modify Date               : 2020:09:08 03:48:27
    #
    # sometimes present:
    # GPS Date/Time                   : 2020:09:06 14:22:11Z
    #
    # $ exiftool alan-dropbox/VID_20200905_155952.mp4 | grep -i date
    # File Modification Date/Time     : 2020:09:05 05:59:52-05:00
    # File Access Date/Time           : 2020:09:13 20:54:48-05:00
    # File Inode Change Date/Time     : 2020:09:13 19:00:08-05:00
    # Create Date                     : 2020:09:05 21:59:52
    # Modify Date                     : 2020:09:05 21:59:52
    # Track Create Date               : 2020:09:05 21:59:52
    # Track Modify Date               : 2020:09:05 21:59:52
    # Media Create Date               : 2020:09:05 21:59:52
    # Media Modify Date               : 2020:09:05 21:59:52
    #
    # and of these, none actually match the timestamp in the filename, which is correct.
    # so that seems to be the most reliable and the easiest way to get the timestamp.
    #
    ######################
    # gps
    # just missing sometimes?
    #
    # exiftool MVIMG_20200906_082212.jpg
    # GPS Altitude                    : 3568.6 m Above Sea Level
    # GPS Date/Time                   : 2020:09:06 14:22:11Z
    # GPS Latitude                    : 35 deg 58' 10.17" N
    # GPS Longitude                   : 105 deg 36' 34.71" W
    # GPS Position                    : 35 deg 58' 10.17" N, 105 deg 36' 34.71" W
    #
    # exiftool VID_20200904_172310.mp4 | grep -i user
    # User Data xyz                   : +35.9119-105.6467/
    #
    # haven't found any GPS data in cody's iphone media

    # these should be checking the exif "Device" or something
    details = {}
    if fname.endswith('jpg'):
        # IMG_20200903_145702.jpg
        #     012345678901234
        details['type'] = 'image'
        basename = os.path.basename(fname)

        m = re.findall('2020[0-9]*_?[0-9]*[^0-9]', basename)
        datestr = m[0]
        Y, M, D = int(datestr[0:4]), int(datestr[4:6]), int(datestr[6:8])
        h, m, s = int(datestr[9:11]), int(datestr[11:13]), int(datestr[13:15])
        ts = datetime.datetime(Y, M, D, h, m, s)
        details['ts'] = datetime.datetime.strftime(ts, '%Y-%m-%dT%H:%M:%S')

        if not ('GPSLatitude' in exif and 'GPSLongitude' in exif):
            details['error'] = 'no GPS'
            return details
        lat_dms = exif['GPSLatitude']
        lon_dms = exif['GPSLongitude']
        details['lat'] = dms_to_dd(lat_dms)
        details['lon'] = dms_to_dd(lon_dms)

        if 'GPSAltitude' in exif:
            m = re.findall('[0-9.]+', exif['GPSAltitude'])
            if m:
                el_m = float(m[0])
                details['elevation'] = m2ft * el_m

    elif fname.endswith('mp4'):
        details['type'] = 'video'
        basename = os.path.basename(fname)

        m = re.findall('2020[0-9]*_?[0-9]*[^0-9]', basename)
        datestr = m[0]
        Y, M, D = int(datestr[0:4]), int(datestr[4:6]), int(datestr[6:8])
        h, m, s = int(datestr[9:11]), int(datestr[11:13]), int(datestr[13:15])
        ts = datetime.datetime(Y, M, D, h, m, s)
        details['ts'] = datetime.datetime.strftime(ts, '%Y-%m-%dT%H:%M:%S')

        if not ('UserDataxyz' in exif):
            details['error'] = 'no GPS'
            return details
        latlon_str = exif['UserDataxyz']
        m  = re.findall('[-+][0-9.]+', latlon_str)
        details['lat'] = float(m[0])
        details['lon'] = float(m[1])

    elif fname.endswith('jpeg'):
        # these files have no GPS data
        return {'error': 'unknown format'}
    elif fname.endswith('mov'):
        # these files have no GPS data
        return {'error': 'unknown format'}
    else:
        # these might be video thumbnails
        return {'error': 'unknown format'}

    return details


def dms_to_dd(dms):
    nums = re.findall('[0-9.]+', dms)
    d, m, s = int(nums[0]), int(nums[1]), float(nums[2])
    dd = d + m/60 + s/3600

    if dms[-1] in 'SW':
        dd = -dd

    return dd


def get_exif_tags(fname):
    # dumb wrapper around CLI exiftool,
    # this formats values better than exifread.process_file
    cmd = 'exiftool "%s"' % fname
    res = subprocess.check_output(cmd, shell=True)
    lines = str(res).strip().split('\\n')
    pairs = [line.split(':', 1) for line in lines]
    tags = {p[0].replace(' ', ''): p[1].strip() for p in pairs if p[0] and len(p)==2}
    return tags



main()
