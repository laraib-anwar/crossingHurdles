FROM python:3.11.9-slim-bookworm@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317

RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    scipy==1.13.0 \
    pandas==2.2.2 \
    python-dateutil==2.9.0.post0 \
    pytz==2026.5 \
    six==1.17.0 \
    tzdata==2026.5

WORKDIR /root

COPY data /root/data
RUN mkdir -p /root/results
