"""Small dependency-free operational counters and sanitized JSON request logs."""
import json
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4


class Operations:
    def __init__(self):
        self.started=time.monotonic()
        self.requests=Counter()
        self.latency_ms=Counter()
        self.logger=logging.getLogger('broadcast.operations')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            self.logger.addHandler(logging.StreamHandler())
        self.logger.propagate=False

    async def middleware(self, request, call_next):
        start=time.monotonic()
        request_id=str(uuid4())
        status=500
        try:
            response=await call_next(request)
            status=response.status_code
            response.headers['X-Request-ID']=request_id
            return response
        finally:
            route=getattr(request.scope.get('route'),'path','unmatched')
            key=(request.method,route,status)
            elapsed=round((time.monotonic()-start)*1000,2)
            self.requests[key]+=1
            self.latency_ms[key]+=elapsed
            # Never log query strings, request/response bodies, keys or session IDs.
            if route not in ['/health/live','/health/ready','/api/ops']:
                self.logger.info(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),
                    request_id=request_id,method=request.method,route=route,status=status,latency_ms=elapsed)))

    def snapshot(self):
        return {'uptime_seconds':round(time.monotonic()-self.started),
            'scope':'This process; counters reset on restart.',
            'requests':[{'method':method,'route':route,'status':status,'count':count,
                'mean_latency_ms':round(self.latency_ms[(method,route,status)]/count,2)}
                for (method,route,status),count in self.requests.items()]}
