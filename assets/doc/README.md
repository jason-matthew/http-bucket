# Overview

Directory captures project intentions, goals, and design.  Content which applies to current version is retained within this document.  Peer documents may dive into a specific topic or retain historical considerations.

## Goals

### Application 

Project provides simple methods for retaining file system content using HTTP.  The core idea here was heavily influenced by local pastebin deployments.  Quickly retaining and sharing snippets offered new ways to collaborate with the sole requirement that two users access the same HTTP location.  

Extending this convention to file and directory storage grants similiar  capabilities.  But more valuable was the ability for misc. processes to retain and share runtime artifacts without depending on local storage.  

This project was initially formed with the goal of granting storage to ephemeral containers.  Portable docker images make it easy to facilitate a short-lived task, however retaining artifacts often complicated runtime requirements.  This project's primary goal is to provide HTTP methods for file retention and acts as an alternative to a host mount, NFS share, or persistent volume.  Additionally, the application and storage methods provided by this project are portable and self-contained.  You can start, stop, suspend, and resume an instance isoloated within your network.

### File support

Producing clients can make a single HTTP call to facilitate file and directory retention.  Individual files, compressed files, and compressed archives are supported.  Content retention is not fixed to blobs.  HTTP server should be capable of unpackaging common file types and retaining local file system content in both original and unpackaged forms.  Doing so simplifies content access for consumers and simplifies collaboration.

### Retention

HTTP server will interrogate uploaded file and attempt to determine mime type.  Additional processing will occur for common compression and archive formats.  The original file and process derivatives will be retained with the HTTP server's file system.  

Content             | Examples | Rational | Retention
--------------------|----------|----------|----------
Standalone file     | script, data structure, log | | blob
Compressed file     | compressed log | Network bandwidth is sparse, file compression has significant gains | blob + uncompressed blob
Directory archive   | tar, zip | Retain directory structure | blob + individual files
Compressed archive  | tgz      | Common Linux use case  | blob + uncompressed blob + individual files

The table above captures increasingly complex scenarios.  In the first, the system chooses to retain just 1 blob/file and clients receive knowledge of an individual checksum.  Other scenarios will trigger a larger set of actions.  Original, intermediary, and unpackaged content will be retained within the blobstore.  Clients receive knowledge of each resource created.

### Storage

HTTP server needs to be cognizant of disk usage.  All content is first retained within a blobstore.  Directory structures are established using hardlinks.  

## History

Author | Date       | Notes
-------|------------|------
JM     | 15Jan2021  | Initial draft