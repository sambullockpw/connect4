#!/usr/bin/env python
import itertools
import json
import asyncio
import websockets
from connect4 import PLAYER1, PLAYER2, Connect4

async def handler(websocket):

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
    async with websockets.serve(handler, "", 8001):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())