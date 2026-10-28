# qa-agent in a container: no Python install needed.
#
#   docker build -t qa-agent https://github.com/rahulsharma-qe/api-qa-agent.git
#   cd your-team-project
#   docker run --rm -v "$PWD:/project" qa-agent check
#
# The tool only (init, import, check, review, generate, trace, promote, flaky, suite, draft, ai-report).
# bug-detection runs your tests, so it runs where they run (pytest or Maven), not in this image.
# The AI layer's model clients are in it: pass the key with -e, e.g. -e ANTHROPIC_API_KEY.
# Your tests run where they always run (pytest or Maven): they call your API, and inside a container
# "localhost" is the container, not your machine.
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/rahulsharma-qe/api-qa-agent" \
      org.opencontainers.image.description="qa-agent: test cases as data, reviewed by a person, turned into API tests"

WORKDIR /opt/qa-agent
COPY pyproject.toml README.md LICENSE ./
COPY qa_agent qa_agent
COPY env_check env_check
COPY demo_api demo_api
RUN pip install --no-cache-dir ".[anthropic,openai]"

# Your project folder is mounted here; qa-agent reads and writes it as if you ran it there.
WORKDIR /project
ENTRYPOINT ["qa-agent"]
CMD ["--help"]
