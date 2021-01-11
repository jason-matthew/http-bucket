#!/usr/bin/env bash
# Compresses ./uploads directory in multiple formats
set -x 
set -e
set -o pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
SRC_DIR="${DIR}/files"
DST_DIR="${DIR}/archives"

# create, verbose, <compression>, file
tar -cvf ${DST_DIR}/upload.tar ${SRC_DIR}/
tar -cvzf ${DST_DIR}/upload.tgz ${SRC_DIR}/
tar -cvjf ${DST_DIR}/upload.bz2 ${SRC_DIR}/
tar -cvJf ${DST_DIR}/upload.xz ${SRC_DIR}/

# recursive, file
zip -r ${DST_DIR}/uploads.zip ${SRC_DIR}
