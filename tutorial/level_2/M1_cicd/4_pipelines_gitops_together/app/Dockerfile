FROM registry.access.redhat.com/ubi9/python-311:latest

WORKDIR /opt/app-root/src

COPY app.py .
COPY test_app.py .

EXPOSE 8080

USER 1001

CMD ["python", "app.py"]
