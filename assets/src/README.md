# Python Overview

Document describes source implementation and summarizes runtime processing

## Modules

The following modules have been implemented with a goal of separating areas of concern.  

Module                          | Description | Notes
--------------------------------|-------------|----------------
[api.py](./api.py)              | Flask application and project entrypoint.  Dictate available endpoints and facilitate high level system actions | 
[bucket.py](./bucket.py)        | Process uploaded files including blob, uncompressed blob, and directory retention.  Manage Blobstore and Dirstore to facilitate artifact retention. | 
[calc.py](./calc.py)            | Determine checksums for file system content | 
[unpackage.py](./unpackage.py)  | Provide standalone functions for decompressing and exploding archives.  | 

