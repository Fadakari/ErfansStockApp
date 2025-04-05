from aplication import app
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from fastapi import Request
from slowapi.errors import RateLimitExceeded

# راه‌اندازی Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# یک نمونه route با محدودیت سرعت
@app.get("/")
@limiter.limit("5/minute")
async def root(request: Request):
    return {"message": "Hello, world"}

if __name__ == "__main__":
    app.run(host="localhost", port=5000, debug=True)
