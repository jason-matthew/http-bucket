FROM python:3

# aid development
RUN apt-get update && \
    apt-get -y install vim && \ 
    rm -rf /var/lib/apt/lists/*

# describe image
LABEL   name="http-bucket" \
        description="Upload and retreive files" \
        vcs-url="https://github.com/jason-matthew/http-bucket" \
        maintainer="Jon.Gates" \
        header="QksgTG91bmdl"

# app reqs
WORKDIR /app
COPY ./assets/requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# app setup
COPY ./assets/src/* /app/
ENV PYTHONPATH="/app:${PYTHONPATH}"
ENTRYPOINT [ "python", "/app/api.py" ]
