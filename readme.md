# Overview

Provide HTTP server to retain and organize files.

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
export ARCHIVE_DIR=/tmp/bucket      # disk storage; consumed by bucket.py
export FLASK_ENV=development        # load codechanges without restarting server

# start flask application
python3 ./assets/src/bucket.py
```

### Upload

Examples provided here present simplified upload instructions.  Application can be configured to organize file system content by specifying tags during service deployment and providing matching headers during file upload.  Additional instructions are captured within [Config](#Config) section.

#### GET, POST, PUT

`/upload` supports:
* `GET`: HTML form which prompts user for upload
* `POST`: Send file and filename via `multipart/form-data`
* `PUT`: Send file directly

Additional data can be conveyed to `PUT` and `POST` operations.  Attributes dictate how content is retained (and replicated) server side.  This config is covered within [Config](#Config) section.

```bash
server=example.org

# POST used to support multipart/form-data; operation is recommended
curl -X POST -F 'file=@results.xml' ${server}/upload

# PUT grants clients another option
curl -X PUT --data 
```

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
curl --head ${server}/checksum/$(md5sum ${artifact} | awk '{print $1}')
curl --head ${server}/checksum/$(shasum -a 256 ${artifact} | awk '{print $1}')
curl --head ${server}/checksum/$(shasum -a 512 ${artifact} | awk '{print $1}')
```

## Config



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