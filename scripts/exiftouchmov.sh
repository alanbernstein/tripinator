#!/bin/bash
# read the "Create Date" exif field from a photo/video file, and
# `touch -t` the file with it so "sort by date" works as expected

# Create Date                     : 2020:09:03 14:56:41  <- from exiftool
# [[CC]YY]MMDDhhmm[.SS]                                  <- -m format for BSD `touch`


for f in *.mov ; do
    cdate=$(exiftool -CREATIONDATE "$f" | cut -d: -f2-)
    Y=$(echo $cdate | cut -d: -f1)
    M=$(echo $cdate | cut -d: -f2)
    D=$(echo $cdate | cut -d: -f3 | cut -d" " -f1)
    h=$(echo $cdate | cut -d: -f3 | cut -d" " -f2)
    m=$(echo $cdate | cut -d: -f4)
    s=$(echo $cdate | cut -d: -f5 | cut -c1-2)

    toucharg="$Y$M$D$h$m.$s"
    echo "$f: '$toucharg'  '$Y' '$M' '$D' '$h' '$m' '$s'"
    touch -mt $toucharg $f
done

