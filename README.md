# Overview

Provide HTTP server to retain and organize files.

Project originally created to provide file storage to ephemeral processes (ie containers).

## Preface

Document provides a quickstart for application deployment and usage.  Project documentation and commentary is retained within additional READMEs.  To name a few:

* [Goals and design](./assets/doc/README.md)
* [Python modules](./assets/src/README.md)

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
    -p ${exposed_port}:80 \
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

# application config
export ARCHIVE_DIR=/tmp/bucket      # disk storage; consumed by bucket.py
export FLASK_ENV=development        # load codechanges without restarting server

# start flask application
python3 ./assets/src/api.py
```

### Upload

Examples provided here present simplified upload instructions.  Application can be configured to organize file system content by specifying tags during service deployment and providing matching headers during file upload.  Additional instructions are captured within [Config](#Config) section.

#### GET, POST

`/upload` supports:
* `GET`: HTML form which prompts user for upload
* `POST`: Send file and filename via `multipart/form-data`

Additional data can be conveyed to `POST` operations via headers.  Attributes dictate how content is retained (and replicated) server side.  This config is covered within [Config](#Config) section.


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

# retreive system config
curl ${server}/config

# check if content previously uploaded
artifact=results.xml
curl --head ${server}/checksum/$(md5sum ${artifact} | awk '{print $1}')
```

## Config

Environment variables can control application behaviors

Variable            | Default               | Description   | Notes
--------------------|-----------------------|---------------|-------
`ARCHIVE_DIR`       | /tmp/bucket/archive   | Local storage path | When deploying via docker, path should be a mounted volume
`CHECKSUM_TYPE`     | md5                   | Hashing algorithm used to calculate file checksum | Supported dictated by [hashlib](https://docs.python.org/3/library/hashlib.html)
`MAX_CONTENT_LENGTH`| 32mb                  | Max file size supported by `/upload` endpoint | `<int><unit>` and `<bytes>` formatted supported

## Future tasks

* [Flask Configure Apache](https://flask.palletsprojects.com/en/1.1.x/deploying/mod_wsgi/#configuring-apache)

## References

Flask

* [Quickstart](https://flask.palletsprojects.com/en/1.1.x/quickstart/#quickstart)
* [Development Server](https://flask.palletsprojects.com/en/1.1.x/server/#server)
* [Upload files](https://flask.palletsprojects.com/en/1.1.x/patterns/fileuploads/)
* [API](https://flask.palletsprojects.com/en/1.1.x/api/)
* [werkzeug FileStorage](https://werkzeug.palletsprojects.com/en/1.0.x/datastructures/#werkzeug.datastructures.FileStorage)
* [ReadTheDocs](https://tedboy.github.io/flask/index.html)

Mime Types

* [Python-magic](https://github.com/ahupp/python-magic)
* [Apache Mime Types](https://svn.apache.org/repos/asf/httpd/httpd/trunk/docs/conf/mime.types)
* [Mozilla Common Mime Types](https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types)
