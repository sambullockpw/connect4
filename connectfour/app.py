#!/usr/bin/env python
import itertools
import json
import asyncio
import os
import signal
from ntpath import join
from sqlite3 import connect
import websockets
import secrets
from connect4 import PLAYER1, PLAYER2, Connect4

JOIN = {}
WATCH = {}

async def replay(websocket, game):
    """
    Send previous moves.

    """
    # Make a copy to avoid an exception if game.moves changes while iteration
    # is in progress. If a move is played while replay is running, moves will
    # be sent out of order but each move will be sent once and eventually the
    # UI will be consistent.
    for player, column, row in game.moves.copy():
        event = {
            "type": "play",
            "player": player,
            "column": column,
            "row": row,
        }
        await websocket.send(json.dumps(event))

async def start(websocket):
    # Initialize a Connect Four game, the set of WebSocket connections
    # receiving moves from this game, and secret access token.
    game = Connect4()
    connected = {websocket}

    join_key = secrets.token_urlsafe(12)
    watch_key = secrets.token_urlsafe(12)
    JOIN[join_key] = game, connected
    WATCH[watch_key] = game, connected

    try:
        # Send the secret access token to the browser of the first player,
        # where it'll be used for building a "join" link.
        event = {
            "type": "init",
            "join": join_key,
            "watch": watch_key,
        }
        await websocket.send(json.dumps(event))

        # Temporary - for testing.
        print("first player started game", id(game))
        #async for message in websocket:
        #    print("first player sent", message)
        await play(websocket, game, PLAYER1, connected)

    finally:
        del JOIN[join_key]

async def error(websocket, message):
    event = {
        "type": "error",
        "message": message,
    }

    await websocket.send(json.dumps(event))

async def join(websocket, join_key):
    # Find the connect four game
    try:
        game, connected = JOIN[join_key]
    except KeyError:
        await error(websocket, "Game not found")
        return
    
    # Register to recieve moves from this game
    connected.add(websocket)
    try:
        # Temporary for testing
        print("second player joined game", id(game))
        #async for message in websocket:
        #    print("second player sent", message)
        await replay(websocket, game)
        await play(websocket, game, PLAYER2, connected)
        
    finally:
        connected.remove(websocket)

async def watch(websocket, watch_key):
    try:
        game, connected = WATCH[watch_key]
    except KeyError:
        await error(websocket, "Game not found")
        return

    connected.add(websocket)
    try:
        await replay(websocket, game) 
        await websocket.wait_closed()
    finally:
        connected.remove(websocket)

    

async def play(websocket, game, player, connected):

    async for message in websocket:
        event = json.loads(message)
        assert event["type"] == "play"
        column = event["column"]

        try:
            # play the move
            row = game.play(player, column)

        except RuntimeError as exc:
            # Send an "error" event if the move was illegal
            await error(websocket, str(exc))
            continue

        # Send a play move to the user interface
        event = {
            "type": "play",
            "player": player,
            "column": column,
            "row": row,
        }
        websockets.broadcast(connected, json.dumps(event))

        if game.winner is not None:
            event = {
                "type": "win",
                "player": game.winner,
            }
            websockets.broadcast(connected, json.dumps(event))


async def handler(websocket):
    # Receive and parse the "init" event from the UI.
    message = await websocket.recv()
    event = json.loads(message)
    assert event["type"] == "init"

    if "join" in event:
        # Second play joins the game
        await join(websocket, event['join'])
    elif "watch" in event:
        await watch(websocket, event['watch'])
    else:
        # First player starts a new game.
        await start(websocket)

async def handler1(websocket):

    game = Connect4()

    turns = itertools.cycle([PLAYER1, PLAYER2])
    player = next(turns)

    async for message in websocket:
        event = json.loads(message)
        assert event["type"] == "play"
        column = event["column"]

        try:
            # play the move
            row = game.play(player, column)
        except RuntimeError as exc:
            # Send an "error" event if the move was illegal
            event = {
                "type": "error",
                "message": str(exc),
            }
            await websocket.send(json.dumps(event))
            continue

        # Send a play move to the user interface
        event = {
            "type": "play",
            "player": player,
            "column": column,
            "row": row,
        }
        await websocket.send(json.dumps(event))

        if game.winner is not None:
            event = {
                "type": "win",
                "player": game.winner,
            }
            await websocket.send(json.dumps(event))

        player = next(turns)


async def main():
    # Set the stop condition when receiving SIGTERM.
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    port = int(os.environ.get("PORT", "8001"))
    async with websockets.serve(handler, "", port):
        await stop


if __name__ == "__main__":
    asyncio.run(main())