#!/usr/bin/env python3

from aiohttp import web
from datetime import datetime
import asyncio
import discord
import json
import random
import re

def log(label, msg): print(f'{datetime.now().strftime("%F %T")} [{label}] {msg}')
emd = discord.utils.escape_markdown
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


class Van:
    def __init__(self, vid, desc, who, holdlist=None):
        self.vid = vid
        self.desc = desc
        self.who = who
        self.holdlist = holdlist or []
    def holds(self): return ', '.join(self.holdlist)
    def serialize(self):
        return { 'vid': self.vid, 'desc': self.desc, 'who': self.who, 'holdlist': self.holdlist }
    def deserialize(obj):
        return Van(obj['vid'], obj['desc'], obj['who'], obj['holdlist'])


class AutoVan:
    def __init__(self, day, hour, minute, desc):
        self.day = day
        self.hour = hour
        self.minute = minute
        self.desc = desc
        self.triggered = False


class Frontend:
    def log(self, msg): log(self.label, msg)

    async def send_new_van(self, desc, who): return await self.backend.send_new_van(self, desc, who)
    async def send_del_van(self, vid): return await self.backend.send_del_van(self, vid)
    async def send_hold_van(self, van, who, isadd): return await self.backend.send_hold_van(self, van, who, isadd)

    async def recv_new_van(self, van): pass
    async def recv_del_van(self, van): pass
    async def recv_update_van(self, van): pass


class DiscordFrontend(Frontend, discord.Client):
    label = 'DISCORD'
    cid = 881689982635487314
    buses = list('🚌🚐🚎🚍')
    vans = {}

    def uname(self, user): return user.name
    def fmt(self, van):
        return f'van: **{emd(van.desc)}**' + \
            (f' *(by {emd(van.who)})*' if van.who else '') + \
            (f' holding for **{emd(van.holds())}**' if van.holdlist else '')

    async def go(self):
        return await self.start(open('token').read())

    async def on_ready(self):
        self.log('started')

    async def on_message(self, message):
        if message.author == self.user or message.channel.id != self.cid: return
        self.channel = message.channel

        if message.content.startswith('van'):
            await self.send_new_van(re.sub(r'^van[: ]*', '', message.content) or '(no description)', self.uname(message.author))
            await message.delete()

    async def on_raw_reaction_add(self, ev): await self.on_react(ev, True)
    async def on_raw_reaction_remove(self, ev): await self.on_react(ev, False)

    async def on_react(self, ev, isadd):
        if ev.user_id == self.user.id or ev.message_id not in self.vans or ev.emoji.name not in self.buses: return
        await self.send_hold_van(self.vans[ev.message_id], self.uname(await self.fetch_user(ev.user_id)), isadd)

    async def recv_new_van(self, van):
        van.msg = await self.channel.send(self.fmt(van))
        self.vans[van.msg.id] = van
        await van.msg.add_reaction(random.choice(self.buses))

    async def recv_update_van(self, van):
        await van.msg.edit(content=self.fmt(van))


class WebFrontend(Frontend):
    label = 'WEB'
    page = re.sub(r'\{\{([^}]*)\}\}', lambda m: open(m.group(1)).read(), open('pardina.html').read())

    def __init__(self):
        self.vans = []
        self.ws = []

    async def go(self):
        runner = web.ServerRunner(web.Server(self.handler))
        await runner.setup()
        await web.TCPSite(runner, 'localhost', 1231).start()
        self.log('started')

    async def handler(self, req):
        self.log(f'{req.remote} {req.method} {req.path}')

        if req.headers.get('Upgrade') == 'websocket':
            ws = web.WebSocketResponse()
            await ws.prepare(req)
            self.ws.append(ws)
            await ws.send_str(json.dumps({
                'type': 'set',
                'vans': [v.serialize() for v in self.vans]
            }))
            async for msg in ws:
                data = json.loads(msg.data)
                if data['type'] == 'hold':
                    await self.send_hold_van(next(v for v in self.vans if v.vid == data['vid']), data['who'], data['isadd'])
            self.ws.remove(ws)
            return

        if req.method == 'GET':
            return web.Response(text=self.page, content_type='text/html')

        return web.Response(text='hi')

    async def recv_new_van(self, van):
        self.vans.append(van)
        await asyncio.gather(*(ws.send_str(json.dumps({
            'type': 'add', 'van': van.serialize()
        })) for ws in self.ws))

    async def recv_update_van(self, van):
        await asyncio.gather(*(ws.send_str(json.dumps({
            'type': 'upd', 'van': van.serialize()
        })) for ws in self.ws))


class AutoFrontend(Frontend):
    label = 'AUTO'
    schedule = [
        # AutoVan(SUN, 5, 7, '17R')
    ]

    async def go(self):
        self.log('started')
        while 1:
            d = datetime.now()
            day, hour, minute = d.weekday(), d.hour, d.minute
            for av in self.schedule:
                if av.day == d.weekday() and av.hour == d.hour and av.minute == d.minute:
                    if not av.triggered: await self.send_new_van(av.desc, None)
                    av.triggered = True
                else:
                    av.triggered = False
            await asyncio.sleep(1)


class Backend():
    def __init__(self):
        self.frontends = [ 0
                         , DiscordFrontend()
                         , WebFrontend()
                         , AutoFrontend()
                         ][1:]
        self.maxvid = 0

    def go(self):
        loop = asyncio.get_event_loop()
        for f in self.frontends:
            f.backend = self
            loop.create_task(f.go())
        loop.run_forever()

    async def send_new_van(self, sender, desc, who):
        van = Van(self.maxvid, desc, who)
        self.maxvid += 1
        await asyncio.gather(*(f.recv_new_van(van) for f in self.frontends))

    async def send_del_van(self, sender, vid):
        pass

    async def send_hold_van(self, sender, van, who, isadd):
        if who in van.holdlist == isadd: return
        van.holdlist.append(who) if isadd else van.holdlist.remove(who)
        await asyncio.gather(*(f.recv_update_van(van) for f in self.frontends))


Backend().go()
