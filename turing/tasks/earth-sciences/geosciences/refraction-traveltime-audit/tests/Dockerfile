FROM python:3.11-slim

# Test dependencies are baked here; nothing is installed at trial time. pytest and
# pytest-json-ctrf are pinned benchmark-wide. numpy and scipy match the agent image, because
# the verifier runs the agent's program, the legacy script and the independent reference.
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    scipy==1.11.4 \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

# Parent directory of the declared artifacts, the unprivileged runner and its sandbox.
RUN mkdir -p /root/results
RUN useradd --create-home --uid 10001 runner && \
    mkdir -p /logs/verifier /sandbox && \
    chmod 755 /sandbox

COPY . /tests/
RUN chmod -R 700 /tests
WORKDIR /tests
