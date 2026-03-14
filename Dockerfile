FROM python:3.14-alpine@sha256:c0ab0a7dbd3817518a4128bbbb6a2672fd3b83c6b4b7a09b871a3c11528cb13a

RUN pip3 install --no-cache-dir boto3==1.42.67

COPY change.py /change.py
ENTRYPOINT ["python3", "/change.py"]
