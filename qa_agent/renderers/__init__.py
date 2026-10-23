"""Renderers: approved cases -> test code for one framework, the same code for the same case, every time.

Each renderer turns a case file into one test file (one test per case) and names each test, which is
how `trace` finds a case's tests.
"""

from qa_agent.renderers.common import GeneratedFile, RenderError
from qa_agent.renderers.python_pytest import PytestRenderer
from qa_agent.renderers.restassured_testng import RestAssuredRenderer

RENDERERS = {"pytest": PytestRenderer(), "restassured": RestAssuredRenderer()}

__all__ = ["GeneratedFile", "RENDERERS", "RenderError"]
