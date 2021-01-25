#!/usr/bin/env bash
# Compresses ./uploads directory in multiple formats
set -x
set -e
set -o pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
SRC_DIR="${DIR}/files"
DST_DIR="${DIR}/archives"

# create, verbose, <compression>, file
cd ${SRC_DIR}
tar -cvf ${DST_DIR}/upload.tar .
tar -cvzf ${DST_DIR}/upload.tgz .
tar -cvjf ${DST_DIR}/upload.bz2 .
tar -cvJf ${DST_DIR}/upload.xz .

# recursive, file
zip -r ${DST_DIR}/upload.zip .
