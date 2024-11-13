# ---------------------------------------------------------
# Do not modify this file. It was generated by `scripts/generate_typed_dicts.py`.
# ---------------------------------------------------------

from typing import Mapping, Optional, TypedDict

import anthropic
import httpx


class ChatBedrockClientArgs(TypedDict, total=False):
    aws_secret_key: str | None
    aws_access_key: str | None
    aws_region: str | None
    aws_profile: str | None
    aws_session_token: str | None
    base_url: str | httpx.URL | None
    timeout: float | anthropic.Timeout | None | anthropic.NotGiven
    max_retries: int
    default_headers: Optional[Mapping[str, str]]
    default_query: Optional[Mapping[str, object]]
    http_client: httpx.AsyncClient
    _strict_response_validation: bool
