"""Serve the simulator on localhost. Run: python web_server.py --open"""
import argparse
import asyncio
from contextlib import suppress
import json
from pathlib import Path
import webbrowser

from aiohttp import web, WSMsgType

from autopilot import ControllerSettings
from simulation import Simulation, DT

WEB_DIR = Path(__file__).resolve().parent / 'web'


@web.middleware
async def local_only(request, handler):
    # Also reject DNS rebinding and cross-site websocket connections.
    host = request.host.split(':')[0]
    if host not in ('127.0.0.1', 'localhost'):
        raise web.HTTPForbidden(text='This simulator accepts localhost requests only')
    origin = request.headers.get('Origin')
    if origin is not None and origin != f'{request.scheme}://{request.host}':
        raise web.HTTPForbidden(text='Open the simulator directly on localhost')
    response = await handler(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob: data:; object-src 'none'; frame-ancestors 'none'"
    return response


def apply_command(simulation, message):
    if not isinstance(message, dict):
        raise ValueError('Expected a command object')
    action = message.get('action')
    if action == 'configure':
        settings = message.get('settings')
        if settings is not None:
            if not isinstance(settings, dict):
                raise ValueError('Controller settings must be an object')
            settings = ControllerSettings(**settings)
        simulation.configure(message.get('x', simulation.platform.x),
                             message.get('y', simulation.platform.y), settings)
    elif action == 'launch':
        simulation.launch()
    elif action == 'pause':
        simulation.pause()
    elif action in ('stop', 'reset'):
        simulation.stop(reset=action == 'reset')
    else:
        raise ValueError('Unknown command')


async def websocket(request):
    socket = web.WebSocketResponse(heartbeat=20, max_msg_size=32768)
    await socket.prepare(request)
    simulation = Simulation(settings=request.app[SETTINGS_KEY])
    # A connection owns its simulation: tabs cannot alter each other's flights.
    async def send(payload):
        await asyncio.wait_for(socket.send_str(json.dumps(payload, allow_nan=False)), timeout=2)

    async def updates():
        loop = asyncio.get_running_loop()
        previous = loop.time()
        accumulator = 0.
        last_history = -1.
        while not socket.closed:
            now = loop.time()
            accumulator += min(now - previous, .1)
            previous = now
            while accumulator >= DT:
                simulation.step()
                accumulator -= DT
            full = simulation.elapsed - last_history >= .5 or simulation.elapsed < last_history
            if full:
                last_history = simulation.elapsed
            await send(simulation.snapshot(include_history=full))
            await asyncio.sleep(1 / 30)

    await send(simulation.snapshot(include_history=True))
    request.app[SOCKETS_KEY].add(socket)
    task = asyncio.create_task(updates())
    # Close the receive loop too if the sender fails (e.g. a stalled client).
    def sender_done(finished):
        if not finished.cancelled() and finished.exception() is not None:
            asyncio.create_task(socket.close())
    task.add_done_callback(sender_done)
    try:
        async for message in socket:
            if message.type == WSMsgType.TEXT:
                try:
                    data = json.loads(message.data)
                    if isinstance(data, dict) and data.get('action') == 'export':
                        await send(dict(type='csv', filename=f'flight-{simulation.flight_id}.csv',
                                        data=simulation.export_recorder().to_csv()))
                    else:
                        apply_command(simulation, data)
                        await send(simulation.snapshot(include_history=True))
                except (ValueError, TypeError, OverflowError) as error:
                    await send(dict(type='error', message=str(error)))
            elif message.type == WSMsgType.ERROR:
                break
    finally:
        request.app[SOCKETS_KEY].discard(socket)
        task.cancel()
        with suppress(asyncio.CancelledError, ConnectionError, asyncio.TimeoutError):
            await task
    return socket


SETTINGS_KEY = web.AppKey('settings', ControllerSettings)
SOCKETS_KEY = web.AppKey('sockets', set)


async def close_sockets(app):
    await asyncio.gather(*(socket.close(code=1001, message=b'Server shutting down')
                           for socket in list(app[SOCKETS_KEY])))


async def index(request):
    return web.FileResponse(WEB_DIR / "index.html")


def create_app(settings=None):
    app = web.Application(middlewares=[local_only])
    app[SETTINGS_KEY] = settings or ControllerSettings()
    app[SOCKETS_KEY] = set()
    app.on_shutdown.append(close_sockets)
    app.router.add_get('/ws', websocket)
    app.router.add_get('/', index)
    app.router.add_static('/static/', WEB_DIR, show_index=False)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--open', action='store_true', help='open the interface in your browser')
    parser.add_argument('--settings', type=Path, help='controller settings JSON')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    settings = ControllerSettings(**json.loads(args.settings.read_text())) if args.settings else None
    app = create_app(settings)
    if args.open:
        async def open_browser(application):
            asyncio.get_running_loop().call_later(.5, webbrowser.open, f'http://127.0.0.1:{args.port}')
        app.on_startup.append(open_browser)
    web.run_app(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
