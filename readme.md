# Overview

Provide HTTP server to upload, retain, and organize files.

Project originally created to provide file storage to ephemeral processes (ie containers).

## Usage

### Development

Container

```bash
# docker config
image=http-bucket
container=bucket
exposed_port=80
local_storage=/tmp/bucket           # host path

# application config
export ARCHIVE_DIR=/tmp/bucket      # container path; consumed by bucket.py
export FLASK_ENV=development        # load code changes without restarting server

# build image
docker build --rm -t "${image}" .

# start in foreground
# create volume for upload/archive directory
# create volume for local python source code
docker run --rm \
    -e FLASK_ENV -e ARCHIVE_DIR \
    -p ${exposed_port}:5000 \
    --volume ${local_storage}:${ARCHIVE_DIR} \
    --volume $(pwd)/assets/src/:/app \
    --name ${container} ${image}
```

Host

```bash
# (optional) setup virtual environment
virtualenv -p python3 ~/venv/bucket
. ~/venv/bucket/bin/activate

# satisfy dependencies
pip install --user -r ./assets/requirements.txt

# debug properties
export FLASK_ENV=development        # load codechanges without restarting server
export ARCHIVE_DIR=/tmp/bucket      # disk storage

# start flask application
python3 ./assets/src/bucket.py
```

### Upload

```bash
server=example.org

# POST using multipart/form-data
# upload individual file
curl -X POST -F 'file=@results.xml' ${server}/upload

# upload directory structure
curl -X POST -F 'file=@results.zip' ${server}/upload
curl -X POST -F 'file=@results.tgz' ${server}/upload
```

### Query

```bash
server=example.org
artifact=results.xml

# check if content previously uploaded
curl -X HEAD ${server}/checksum/$(md5sum ${artifact} | awk '{print $1}')
curl -X HEAD ${server}/checksum/$(shasum -a 256 ${artifact} | awk '{print $1}')
curl -X HEAD ${server}/checksum/$(shasum -a 512 ${artifact} | awk '{print $1}')
```

## References

Flask

* [Quickstart](https://flask.palletsprojects.com/en/1.1.x/quickstart/#quickstart)
* [Development Server](https://flask.palletsprojects.com/en/1.1.x/server/#server)
* [Upload files](https://flask.palletsprojects.com/en/1.1.x/patterns/fileuploads/)
* [werkzeug FileStorage](https://werkzeug.palletsprojects.com/en/1.0.x/datastructures/#werkzeug.datastructures.FileStorage)

Mime Types

* [Python-magic](https://github.com/ahupp/python-magic)
* [Apache Mime Types](https://svn.apache.org/repos/asf/httpd/httpd/trunk/docs/conf/mime.types)
* [Mozilla Common Mime Types](https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types)