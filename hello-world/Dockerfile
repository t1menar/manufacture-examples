# One Dockerfile for all four Hello World modules:
#   docker build --build-arg MODULE=hello --build-arg SDK_REF=<sha> -t localhost:5001/mf-hello-hello:0.1.0 .
# (`make images` reads SDK_REF from ../versions.env.)
FROM python:3.12-slim

ARG SDK_REPO=https://github.com/t1menar/manufacture-sdk-python
ARG SDK_REF
RUN test -n "${SDK_REF}" \
 && pip install --no-cache-dir "manufacture-sdk @ ${SDK_REPO}/archive/${SDK_REF}.tar.gz"

ARG MODULE
WORKDIR /app
COPY modules/${MODULE}/main.py ./main.py

ENV PYTHONUNBUFFERED=1
USER 65532:65532
EXPOSE 8081
CMD ["python", "main.py"]
