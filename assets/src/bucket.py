"""
Simple Flask application
Provide HTTP service which supports file upload, rentention, and organization

Endpoints provide
    /upload : allow clients to POST files, including archives (ie zip)
    /query  : allow clients to check if content previously uploaded
"""
# core modules
import logging
import os 
import re
import shutil       # check available disk 
import tempfile

# installed modules
from flask import Flask, flash, request, redirect, url_for, send_from_directory, abort
from werkzeug.utils import secure_filename

# local modules
import util

# external config
MAX_CONTENT_LENGTH = os.environ.get("MAX_CONTENT_LENGTH", "32mb").lower()
ARCHIVE_DIR = os.environ.get("ARCHIVE_DIR", "/tmp/bucket/archive")
TEMP_DIR = os.environ.get("ARCHIVE_TEMP_DIR", None)

# CONSTANTS
DISK_SPACE_REQUIRED = 2**30         # 1 gb
DISK_INODE_REQUIRED = 10**6         # 1 million

# globals
logger = util.init_logger(__name__)
app = Flask(__name__)
app.secret_key = "It's ok if clients modify my cookies"

def verify_config():
    """
    Consume external config
    Raise exception for invalid values
    """
    error_msg = (
        "Invalid input provided.  "
        "Unwilling to start HTTP server"
    )
    inputs = {}
    max_content_regex = re.compile("^(\d+)(gb|mb|kb)?$")
    if max_content_regex.search(MAX_CONTENT_LENGTH):
        count, unit = max_content_regex.findall(MAX_CONTENT_LENGTH)[0]
        count = int(count)
        if unit == "gb":
            count = count * 2**30
        elif unit == "mb":
            count = count * 2**20
        elif unit == "kb":
            count = count * 2**10
        inputs['MAX_CONTENT_LENGTH'] = count
    else:
        raise EnvironmentError(
            "Invalid MAX_CONTENT_LENGTH format: '%s'."
            "<# bytes> or <#><unit> required (ie, 10mb).  %s"
            % (MAX_CONTENT_LENGTH, error_msg)
        )
    
    if os.path.isdir(ARCHIVE_DIR):
        pass
    elif os.path.exists(ARCHIVE_DIR):
        raise EnvironmentError(
            "Invalid ARCHIVE_DIR: '%s'.  "
            "Location exists but is not a directory.  %s"
            % (ARCHIVE_DIR, error_msg)
        )
    else:
        # attempt to create location
        try:
            logger.info(
                "Creating ARCHIVE_DIR: '%s'"
                % ARCHIVE_DIR
            )
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            app.config['UPLOAD_FOLDER'] = ARCHIVE_DIR
        except Exception as e:
            raise EnvironmentError(
                "Failed to create ARCHIVE_DIR: '%s'.  %s.  %s"
                % (ARCHIVE_DIR, e, error_msg)
            )
    inputs['UPLOAD_FOLDER'] = ARCHIVE_DIR
    
    # check disk
    avail_bytes, avail_inodes = util.check_disk(ARCHIVE_DIR)

    if avail_bytes < DISK_SPACE_REQUIRED:
        available_gb = round(avail_bytes / 2**30, 2)
        required_gb = round(DISK_SPACE_REQUIRED / 2**30, 2)
        raise EnvironmentError(
            "ARCHIVE_DIR does not have sufficient space.  "
            "%s GB required, but only %s GB available.  %s"
            % (required_gb, available_gb, error_msg)
        )
    if avail_inodes < DISK_INODE_REQUIRED:
        raise EnvironmentError(
            "ARCHIVE_DIR does not have sufficient inodes.  "
            "%s required, but only %s available.  %s"
            % (DISK_INODE_REQUIRED, avail_inodes, error_msg)
        )

    logger.info(
        "Inputs accepted.  Applying config: %s"
        % inputs
    )
    app.config.update(inputs)

@app.route('/', methods=['GET'])
def context_root():
    return "http-bucket server"

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            abort(400, 'File not provided via multi-part form')
        file = request.files['file']
        # if user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            abort(400, 'No selected file')
            return redirect(request.url)
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            # TODO: conditionally redirect if browser was used to POST file
            return redirect(url_for('uploaded_file', filename=filename))
    return '''
    <!doctype html>
    <title>Upload new File</title>
    <h1>Upload new File</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file>
      <input type=submit value=Upload>
    </form>
    '''

@app.route('/upload/v2', methods=['POST'])
def upload_file_v2():
    # check if the post request has the file part
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    file = request.files['file']
    logger.info(
        "File: (%s, %s)" 
        % (type(file), file)
    )
    logger.info(file.__dict__)
    logger.info(
        "Request: (%s, %s)"
        % (type(request), request)
    )
    logger.info(request.__dict__.keys())
    # if user does not select file, browser also
    # submit an empty part without filename
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return {"status": "success", "file": filename}


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    verify_config()
    logger.info(
        "Starting Flask App with config: %s"
        % app.config
    )
    app.run(host='0.0.0.0')