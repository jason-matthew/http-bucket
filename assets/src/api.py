"""
Simple Flask application
Provide HTTP service which supports file upload, rentention, and organization

Endpoints provide
    /upload : allow clients to POST files, including archives (ie zip)
    /query  : allow clients to check if content previously uploaded
"""
# core modules
import logging

import json
import os 
import re
import shutil       # check available disk 
import tempfile
import uuid         # generate unique locations within staging directory

# installed modules
from flask import Flask, flash, request, redirect, url_for, send_from_directory, abort
from werkzeug.utils import secure_filename

# local modules
import bucket
import config
import util

# globals
logger = util.init_logger(__name__)
app = Flask(__name__)
app.secret_key = "It's ok if clients modify my cookies"


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
        # ensure user selected a file
        if file.filename == '':
            abort(400, 'No file selected')
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            # TODO: conditionally redirect if browser was used to POST file
            return redirect(url_for('uploaded_file', filename=filename))
    # GET: provide HTML form
    return '''
    <!doctype html>
    <title>Upload new File</title>
    <h1>Upload new File</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file>
      <input type=submit value=Upload>
    </form>
    '''

@app.route('/upload/inspect', methods=['GET', 'POST'])
def upload_file_v2():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            abort(400, 'File not provided via multi-part form')
        file = request.files['file']
        logger.info(
            "File: (%s, %s)\nFile dict:%s\nFile dir:%s\n\n" 
            % (type(file), file, file.__dict__.keys(), dir(file))
        )
        logger.info(
            "Request: (%s, %s)\nRequest dict:%s\nRequest dir:%s\n\n"
            % (type(request), request, request.__dict__.keys(), dir(request))
        )
        logger.info(
            "Header: (%s, %s)\nHeader dict:%s\nHeader dir:%s\n\n"
            % (type(request.headers), request.headers, request.headers.__dict__.keys(), dir(request.headers))
        )
        misc = {
            "md5": request.content_md5,
            "content-type": request.content_type,
            # "data": request.data,  # bytes object
        }
        logger.info(
            "Misc:\n%s\n\n"
            % (json.dumps(misc, indent=4, sort_keys=True))
        )
        # ensure user selected a file
        if file.filename == '':
            abort(400, 'No file selected')
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return {"status": "success", "file": filename}
    # GET: provide HTML form
    return '''
    <!doctype html>
    <title>Upload new File</title>
    <h1>Upload new File</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file>
      <input type=submit value=Upload>
    </form>
    '''


@app.route('/upload/blob', methods=['POST'])
def upload_file_v3():
    if request.method == 'POST':
        # ensure multipart form completed
        if 'file' not in request.files:
            return {
                "status": "bad request",
                "code": 400,
                "error": "File not provided via multi-part form",
            }, 400
        file = request.files['file']
        if file.filename == '':
            return {
                "status": "bad request",
                "code": 400,
                "error": "No file selected",
            }, 400

        # process upload
        blob = bucket.Blob(file.filename)
        file.save(blob.fpath)
        blob.process()

        if blob.exception:
            return {
                "status": "blob processing failed", 
                "code": 507,
                "error": blob.error
            }, 507

        """
        # WIP
        # spot-check file type
        # decompress archive and retain blobs
        if blob.mime in bucket.Archive.SUPPORTED_MIMETYPES:
            logger.info(
                "File is a supported compressed archive: '%s'"
                % blob.mime
            )
            archive = bucket.Archive(blob.fpath)
            archive.process()
        """
        
        result = {
            "status": "success", 
            "code": 200,
            "checksum": blob.checksum,
        }
        return result, 200    


@app.route('/download/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    inputs = config.source_config()
    app.config.update(inputs)
    logger.info(
        "Starting Flask App with config: %s"
        % app.config
    )
    app.run(host='0.0.0.0')