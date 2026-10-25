"""One-worker production entry point for the SQLite-backed demo."""
import os
import uvicorn


if __name__=='__main__':
    if os.getenv('WEB_CONCURRENCY','1')!='1':
        raise SystemExit('SQLite workflow currently requires exactly one worker and one app instance.')
    os.environ['REQUIRE_FRONTEND_BUILD']='1'
    uvicorn.run('backend.main:app',host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','8080')),
                workers=1,access_log=False,timeout_keep_alive=5)
