"""Is the environment ready? Call the health endpoint of every service a team depends on, before
any test runs, so a service that is down is reported as an environment problem, not a product bug.

    python -m env_check --env qa2 --environments config/environments.yaml --dependencies config/dependencies.yaml

Exit codes: 0 ready · 2 setup problem (a file or setting is wrong) · 3 not ready (a critical service is down).
"""

from env_check.readiness import CheckResult, ReadinessReport, check_environment
from env_check.settings import Dependency, ReadinessSettings, SetupError, load_settings

__all__ = ["CheckResult", "Dependency", "ReadinessReport", "ReadinessSettings", "SetupError", "check_environment",
           "load_settings"]
