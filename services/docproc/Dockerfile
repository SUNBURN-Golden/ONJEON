FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docproc.py /app/docproc.py
RUN python3 -c 'import docproc; assert docproc.tool_version().startswith("24.02.")'
USER 65532:65532
ENTRYPOINT ["python3", "-B", "/app/docproc.py"]
