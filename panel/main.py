import asyncio
import logging
import secrets
import threading
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from .backups import Backups
from .config import Settings
from .minecraft import Minecraft, log_tail
from .monitor import Monitor
from .security import tailscale_identity
from .store import Store
from .spark import SparkReports
from .retention import Retention


class LockedFileResponse(FileResponse):
    def __init__(self, *args, operation_lock, **kwargs):
        super().__init__(*args, **kwargs)
        self.operation_lock = operation_lock

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.operation_lock.release()


class Action(BaseModel):
    action: Literal['start', 'stop', 'restart', 'verify', 'restore', 'spark']
    backup: str = Field(default='', max_length=160)
    confirm: str = Field(default='', max_length=200)


def create_app(settings=None):
    settings = settings or Settings.load()
    store = Store(settings.state / 'panel.sqlite3')
    backups = Backups(settings.root, store)
    minecraft = Minecraft(settings)
    spark = SparkReports(settings.root)
    monitor = Monitor(minecraft, backups, store)
    operation_lock = threading.Lock()
    retention = Retention(backups, operation_lock, settings.backup_keep if not settings.demo else 0)
    job = {'state': 'idle', 'message': 'Nenhuma operação em andamento'}
    csrf = secrets.token_urlsafe(32)
    last_action = [0.0]

    @asynccontextmanager
    async def lifespan(app):
        if not settings.demo:
            monitor.thread.start()
            if retention.keep:
                retention.thread.start()
        yield
        if not settings.demo:
            monitor.close()
            if retention.keep:
                retention.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings, app.state.monitor = settings, monitor

    @app.middleware('http')
    async def protect(request, call_next):
        try:
            if settings.demo and request.client.host in {'127.0.0.1', '::1', 'testclient'}:
                actor = 'Demonstração local (somente leitura)'
            else:
                actor = await asyncio.to_thread(tailscale_identity, request.client.host, settings.owner)
            if request.method not in {'GET', 'HEAD'}:
                origin = request.headers.get('origin')
                if (request.headers.get('x-panel-csrf') != csrf
                        or (origin and origin != str(request.base_url).rstrip('/'))):
                    return JSONResponse({'detail': 'Requisição recusada. Recarregue o painel.'}, status_code=403)
            request.state.actor = actor
            response = await call_next(request)
        except PermissionError as exc:
            response = JSONResponse({'detail': str(exc)}, status_code=403)
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        return response

    @app.get('/api/status')
    def status(request: Request):
        return {**monitor.status, 'actor': request.state.actor, 'csrf': csrf,
                'demo': settings.demo, 'job': dict(job), 'name': settings.process,
                'retention': dict(retention.status)}

    @app.get('/api/logs')
    def logs():
        return {'text': log_tail(settings.root), 'sampled_at': time.time()}

    @app.get('/api/logs/download')
    def download_logs():
        return PlainTextResponse(log_tail(settings.root), headers={'Content-Disposition': 'attachment; filename=minecraft-recent.log'})

    @app.get('/api/backups')
    def list_backups():
        return backups.listing()

    @app.get('/api/backups/{name}/content')
    def content(name: str):
        if not operation_lock.acquire(blocking=False):
            raise HTTPException(409, 'Há uma operação de manutenção em andamento. Tente novamente.')
        try:
            return backups.inspect(name)
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            operation_lock.release()

    @app.get('/api/backups/{name}/download')
    def download(name: str, request: Request):
        if not operation_lock.acquire(blocking=False):
            raise HTTPException(409, 'Há uma operação de manutenção em andamento. Tente novamente.')
        try:
            path, _ = backups.validated(name)
            store.audit(request.state.actor, 'download', name, 'solicitado')
            return LockedFileResponse(path, filename=path.name, media_type='application/zip', operation_lock=operation_lock)
        except (ValueError, OSError) as exc:
            operation_lock.release()
            raise HTTPException(400, str(exc)) from exc
        except BaseException:
            operation_lock.release()
            raise

    @app.get('/api/audit')
    def audit():
        return store.events()

    @app.get('/api/spark')
    def spark_list():
        return spark.listing()

    @app.get('/api/spark/{name}')
    def spark_report(name: str):
        try:
            return spark.read(name)
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    def run_action(payload, actor):
        def progress(message):
            job.update(message=message)
        try:
            if payload.action == 'spark':
                previous = {r['name'] for r in spark.listing()}
                progress('Solicitando análise spark de 60 segundos, com salvamento local.')
                minecraft.capture_spark()
                deadline = time.monotonic() + 100
                while time.monotonic() < deadline:
                    reports = [r for r in spark.listing() if r['name'] not in previous]
                    if reports:
                        spark.read(reports[0]['name'])
                        result = {'message': 'Relatório spark disponível na aba Desempenho.', 'report': reports[0]['name']}
                        break
                    time.sleep(2)
                else:
                    raise RuntimeError('Nenhum relatório concluído foi encontrado. O jogo pode estar travado, reiniciando ou com outro profiler ativo. Consulte os logs; não houve reinício solicitado pelo painel.')
            elif payload.action == 'verify':
                result = backups.inspect(payload.backup, verify=True)
            elif payload.action == 'restore':
                result = backups.restore(payload.backup, minecraft, progress)
            else:
                if payload.action in {'stop', 'restart'}:
                    progress('Aguardando salvamento e parada do Minecraft')
                    minecraft.stop()
                if payload.action in {'start', 'restart'}:
                    progress('Solicitando início ao PM2')
                    minecraft.start()
                result = {'message': 'Comando concluído. A prontidão do jogo será conferida pelo monitoramento.'}
            job.update(state='success', message=result.get('message', 'Integridade verificada com sucesso.'), result=result)
            store.audit(actor, payload.action, payload.backup or settings.process, 'sucesso')
        except Exception as exc:
            logging.exception('Minecraft panel operation failed: %s', payload.action)
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Operação não concluída. Consulte os logs do painel; o jogo pode permanecer parado.'
            job.update(state='error', message=message)
            store.audit(actor, payload.action, payload.backup or settings.process, message)
        finally:
            operation_lock.release()

    @app.post('/api/actions', status_code=202)
    def action(payload: Action, request: Request):
        if settings.demo:
            raise HTTPException(403, 'Demonstração: comandos desabilitados.')
        if payload.action in {'stop', 'restart', 'restore'}:
            expected = payload.backup if payload.action == 'restore' else payload.action
            if not expected or payload.confirm != expected:
                raise HTTPException(400, 'Confirmação obrigatória.')
        if payload.action in {'verify', 'restore'}:
            try:
                backups.validated(payload.backup)
            except (ValueError, OSError) as exc:
                raise HTTPException(400, str(exc)) from exc
        if time.monotonic()-last_action[0] < 5:
            raise HTTPException(429, 'Aguarde alguns segundos antes de enviar outro comando.')
        if not operation_lock.acquire(blocking=False):
            raise HTTPException(409, 'Já existe uma operação em andamento.')
        last_action[0] = time.monotonic()
        job.clear()
        job.update(state='running', action=payload.action, message='Operação iniciada', started=time.time())
        try:
            store.audit(request.state.actor, payload.action, payload.backup or settings.process, 'iniciado')
            threading.Thread(target=run_action, args=(payload, request.state.actor), daemon=True).start()
        except Exception:
            job.update(state='error', message='Não foi possível registrar ou iniciar a operação.')
            operation_lock.release()
            raise
        return dict(job)

    static = Path(__file__).parent / 'static'

    @app.get('/')
    def index():
        return FileResponse(static / 'index.html')

    @app.get('/favicon.ico', include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @app.get('/assets/{name}')
    def asset(name: str):
        if name not in {'app.js', 'style.css', 'spark.js'}:
            raise HTTPException(404)
        return FileResponse(static / name)

    return app
