# qa-agent in a container: no Python install needed.
#
#   docker build -t qa-agent https://github.com/rahulsharma-qe/api-qa-agent.git
#   cd your-team-project
#   docker run --rm -v "$PWD:/project" qa-agent check
#
# The tool only (init, import, check, review, generate, trace, promote, track). Your tests run where
# they always run (pytest or Maven): they call your API, and inside a container "localhost" is the
# container, not your machine.
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/rahulsharma-qe/api-qa-agent" \
      org.opencontainers.image.description="qa-agent: test cases as data, reviewed by a person, turned into API tests"

WORKDIR /opt/qa-agent
COPY pyproject.toml README.md LICENSE ./
COPY qa_agent qa_agent
COPY env_check env_check
COPY mock_service mock_service
RUN pip install --no-cache-dir .

# Your project folder is mounted here; qa-agent reads and writes it as if you ran it there.
WORKDIR /project
ENTRYPOINT ["qa-agent"]
CMD ["--help"]
