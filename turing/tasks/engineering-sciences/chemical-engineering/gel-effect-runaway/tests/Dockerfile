FROM python:3.11.9-slim-bookworm@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317

# pytest and pytest-json-ctrf are pinned benchmark-wide and baked here, never
# installed at trial time (check-pytest-version, check-verifier-tooling-baked).
RUN pip install --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5 \
    iniconfig==2.3.1 \
    packaging==26.3 \
    pluggy==1.6.0 \
    pygments==2.21.0

# The cure-program check runs the agent's bath program through the plant model
# (tests/plant.py); same numerical stack as the agent image.
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    scipy==1.13.0

# Parent directory of the declared artifact, and the verifier log directory.
RUN mkdir -p /root/results /logs/verifier

# Test suite plus verifier-only truth (tests/truth/).
COPY . /tests/
