FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac AS base
RUN apt-get update && apt-get install -y --no-install-recommends python3 poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docproc.py /app/docproc.py
RUN python3 -c 'import docproc; assert docproc.tool_version().startswith("24.02.")'
USER 65532:65532
ENTRYPOINT ["python3", "-B", "/app/docproc.py"]

FROM base AS test
USER 0:0
RUN apt-get update && apt-get install -y --no-install-recommends python3-pytest && rm -rf /var/lib/apt/lists/*
COPY tests /app/tests
COPY test_sandbox.sh /app/test_sandbox.sh
USER 65532:65532

FROM base AS runtime
