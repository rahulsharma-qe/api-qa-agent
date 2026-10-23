"""One error shape for every failure:  {"error": {"code": "...", "message": "..."}}

A test can always read `error.code`, whether the request was invalid, unauthorised or not found.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODES_BY_STATUS = {400: "bad_request", 401: "unauthorized", 404: "not_found", 405: "method_not_allowed",
                   409: "conflict", 422: "invalid_request"}


class ApiError(Exception):
    """An expected failure with its HTTP status, a stable code and a readable message."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, error: ApiError):
        return JSONResponse(error_body(error.code, error.message), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(error_body("invalid_request", _describe(error)), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, error: StarletteHTTPException):
        code = CODES_BY_STATUS.get(error.status_code, "error")
        return JSONResponse(error_body(code, str(error.detail)), status_code=error.status_code)


def _describe(error: RequestValidationError) -> str:
    """'email: not a valid email address; amount: must be 0 or more' — field first, then the reason."""
    parts = []
    for problem in error.errors():
        field = ".".join(str(part) for part in problem.get("loc", ()) if part != "body")
        message = str(problem.get("msg", "invalid")).removeprefix("Value error, ")
        parts.append(f"{field}: {message}" if field else message)
    return "; ".join(parts)
