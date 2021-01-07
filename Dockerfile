FROM python:3
LABEL   name="bucket-archive" \
        description="Upload and retreive files" \
        vcs-url="https://github.com/jason-matthew/bucket" \
        maintainer="Jon.Gates" \
        header="QksgTG91bmdl"

# app setup
WORKDIR /app
COPY ./assets/requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY ./assets/src/* /app/
ENTRYPOINT [ "python", "/app/bucket.py" ]
