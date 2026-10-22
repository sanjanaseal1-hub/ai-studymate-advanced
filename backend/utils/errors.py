"""App-level exceptions. `user_message` is safe to show users; `log_detail` only goes to the log."""


class AppError(Exception):
    def __init__(self, status_code: int, user_message: str, log_detail: str = "", retryable: bool = False):
        super().__init__(user_message)
        self.status_code = status_code
        self.user_message = user_message
        self.log_detail = log_detail
        self.retryable = retryable  # transient failure worth retrying (rate limit, timeout, 5xx)


class LLMError(AppError):
    """Gemini (generation or embedding) failed."""


class DocumentError(AppError):
    """Upload, parsing, or retrieval problem caused by the input."""
