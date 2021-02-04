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


@app.route('/config', methods=["GET"])
def external_config():
    return config.source_external_config(), 200


@app.route('/upload/inspect', methods=['GET', 'POST'])
def upload_inspect():
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
            return {
                "status": "file not retained",
                "file": file.filename
            }, 200
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


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        # ensure multipart form completed
        if 'file' not in request.files:
            return {
                "status": "bad request",
                "code": 400,
                "error": "File not provided via multi-part form",
            }, 400
        file_upload = request.files['file']
        if file_upload.filename == '':
            return {
                "status": "bad request",
                "code": 400,
                "error": "No file selected",
            }, 400

        # process upload
        manager = bucket.Upload(file_upload.filename)
        file_upload.save(manager.get_upload_destination())
        manager.process()
        return manager.get_api_response()
    else:
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


if __name__ == '__main__':
    inputs = config.source_external_config()
    app.config.update(inputs)
    logger.info(
        "Starting Flask App with config: %s"
        % app.config
    )
    app.run(host='0.0.0.0', port=80)