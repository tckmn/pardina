#!/usr/bin/env python3

from aiohttp import web
from datetime import datetime
import asyncio
import discord
import json
import random
import re

logfile = open('log', 'a')
def log(label, msg):
    s = f'{datetime.now().strftime("%F %T")} [{label}] {msg}'
    print(s)
    print(s, file=logfile, flush=True)
emd = discord.utils.escape_markdown
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
WHERE_IS_THE_VAN = 0
WHERE_DEFAULT = 'lot by rage'


class Van:
    def __init__(self, vid, desc, who, holdlist=None, msgid=None):
        self.vid = vid
        self.desc = desc
        self.who = who
        self.holdlist = holdlist or []
        self.msgid = msgid
        self.msg = None
    def holds(self): return ', '.join(self.holdlist)
    def serialize(self, full=False):
        return { 'vid': self.vid, 'desc': self.desc, 'who': self.who, 'holdlist': self.holdlist, **({ 'msgid': self.msgid } if full and self.msgid else {}) }
    def deserialize(obj):
        return Van(obj['vid'], obj['desc'], obj['who'], obj['holdlist'], obj['msgid'])


class AutoVan:
    def __init__(self, day, hour, minute, desc):
        self.day = day
        self.hour = hour
        self.minute = minute
        self.desc = desc
        self.triggered = False
    def __str__(self):
        return f'{self.day} {self.hour} {self.minute} {self.desc}'


class Frontend:
    def __init__(self, *args, **kwargs):
        self.backend = kwargs['backend']

    def log(self, msg): log(self.label, msg)
    def warn(self, msg): log(self.label, f'WARN {msg}')

    async def send_new_van(self, desc, who): return await self.backend.send_new_van(self, desc, who)
    async def send_del_van(self, vid): return await self.backend.send_del_van(self, vid)
    async def send_hold_van(self, van, who, isadd): return await self.backend.send_hold_van(self, van, who, isadd)
    async def send_custom(self, mtype, data): return await self.backend.send_custom(self, mtype, data)

    async def recv_new_van(self, van): pass
    async def recv_del_van(self, van): pass
    async def recv_update_van(self, van): pass
    async def recv_custom(self, mtype, data): pass


class DiscordFrontend(Frontend, discord.Client):
    label = 'DISCORD'
    cid_pub = 881689982635487314
    cid_debug = 883708092603326505
    admin = [133105865908682752]
    buses = list('🚌🚐🚎🚍🦈')
    normal_buses = 4
    places = {
        '😡': 'lot by rage',
        '🗽': 'albany garage',
        '❓': 'a mystery location'
    }

    def uname(self, user): return user.name
    async def fmt(self, van):
        return f'van: **{emd(van.desc)}**' + \
            (f' *(by {emd(van.who)})*' if van.who else '') + \
            (f' holding for **{emd(van.holds())}**' if van.holdlist else '')
    async def where(self):
        if not self.whereid: return None
        wheremsg = await self.channel.fetch_message(self.whereid)
        rlist = [(self.places[r.emoji], r.count)
                 for r in wheremsg.reactions
                 if r.emoji in self.places.keys() and r.count > 1]
        self.log(f'rlist for where: {repr(rlist)}')
        self.whereid = None
        return max(rlist, key=lambda x: x[1], default=(WHERE_DEFAULT,))[0]

    def __init__(self, *args, **kwargs):
        Frontend.__init__(self, *args, **kwargs)
        discord.Client.__init__(self)
        self.silent = self.backend.debug
        self.whereid = None

    async def go(self):
        return await self.start(open('token').read())

    def set_channel(self):
        self.channel = self.channel_debug if self.silent else self.channel_pub

    async def on_ready(self):
        self.channel_pub = self.get_channel(self.cid_pub)
        self.channel_debug = self.get_channel(self.cid_debug)
        self.set_channel()
        await self.backend.load()
        self.log('started')

    async def on_message(self, message):
        if message.author.id in self.admin and message.content.startswith('!'):
            cmd, *args = message.content[1:].split(None, 1)
            if hasattr(self, f'admin_{cmd}'):
                await message.channel.send(await getattr(self, f'admin_{cmd}')(args[0] if args else None) or '[done]')
                return

        if message.author == self.user or message.channel.id not in [self.cid_pub, self.cid_debug]: return

        if message.content.lower().startswith('van'):
            await self.send_new_van(re.sub(r'(?i)^van[: ]*', '', message.content) or '(no description)', self.uname(message.author))
            await message.delete()

    async def on_raw_reaction_add(self, ev): await self.on_react(ev, True)
    async def on_raw_reaction_remove(self, ev): await self.on_react(ev, False)

    async def on_react(self, ev, isadd):
        if ev.user_id == self.user.id or ev.emoji.name not in self.buses: return
        v = self.backend.by_msgid(ev.message_id)
        if not v: return
        await self.send_hold_van(v, self.uname(await self.fetch_user(ev.user_id)), isadd)

    async def recv_new_van(self, van):
        van.msg = await self.channel.send(await self.fmt(van))
        van.msgid = van.msg.id
        await van.msg.add_reaction(random.choice(
            self.buses[:self.normal_buses] if random.random() < 0.95 else
            self.buses[self.normal_buses:]))

    async def recv_update_van(self, van):
        if van.msg: await van.msg.edit(content=await self.fmt(van))
        else: self.log(f'van {van.vid} tried to update with no msg')

    async def recv_custom(self, mtype, data):
        if mtype == WHERE_IS_THE_VAN:
            wheremsg = await self.channel.send(f'where is the van (default: {WHERE_DEFAULT})')
            for place in self.places.keys(): await wheremsg.add_reaction(place)
            self.whereid = wheremsg.id

    async def admin_eval(self, args): return f'```\n{repr(eval(args))}\n```'
    async def admin_await(self, args): return f'```\n{repr(await eval(args))}\n```'
    async def admin_silent(self, args): self.silent = args == '1'; self.set_channel(); return f'silent: {self.silent}'
    async def admin_dump(self, args): return json.dumps([v.serialize() for v in self.backend.vans])
    async def admin_schedule(self, args):
        if args:
            self.backend.auto.read_schedule(args)
            return 'new schedule set'
        else:
            return '```\n' + '\n'.join(map(str, self.backend.auto.schedule)) + '\n```'


class WebFrontend(Frontend):
    label = 'WEB'
    page = lambda *_: re.sub(r'\{\{([^}]*)\}\}', lambda m: open(m.group(1)).read(), open('pardina.html').read())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws = []

    def fix_ws(self):
        oldlen = len(self.ws)
        self.ws = [ws for ws in self.ws if not ws._closing and not ws._closed]
        if len(self.ws) < oldlen: self.log(f'fixed websockets x{oldlen - len(self.ws)}')

    async def broadcast(self, msg):
        if not self.ws: return
        self.fix_ws()
        await asyncio.wait([ws.send_str(json.dumps(msg)) for ws in self.ws])

    async def go(self):
        runner = web.ServerRunner(web.Server(self.handler))
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', 1231).start()
        self.log('started')

    async def handler(self, req):
        self.log(f'{req.remote} {req.method} {req.path}')

        if req.headers.get('Upgrade') == 'websocket':
            ws = web.WebSocketResponse()
            wsid = int(random.random()*10000)
            await ws.prepare(req)
            self.ws.append(ws)
            self.log(f'websocket {wsid} opened')
            await ws.send_str(json.dumps({
                'type': 'set',
                'vans': [v.serialize() for v in self.backend.vans]
            }))
            async for msg in ws:
                self.log(f'websocket {wsid} sent {msg.data}')
                data = json.loads(msg.data)
                if data['type'] == 'hold':
                    await self.send_hold_van(next(v for v in self.backend.vans if v.vid == data['vid']), data['who'], data['isadd'])
            if ws in self.ws: self.ws.remove(ws)
            self.log(f'websocket {wsid} closed')
            return

        if req.method == 'GET':
            return web.Response(text=self.page(), content_type='text/html')

        return web.Response(text='hi')

    async def recv_new_van(self, van):
        await self.broadcast({ 'type': 'add', 'van': van.serialize() })

    async def recv_update_van(self, van):
        await self.broadcast({ 'type': 'upd', 'van': van.serialize() })


class AutoFrontend(Frontend):
    label = 'AUTO'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_schedule()

    def read_schedule(self, sched=None):
        self.schedule = [(lambda a,b,c,d:AutoVan(int(a),int(b),int(c),d))(*line.split()) for line in (sched or open('schedule').read()).split('\n') if line.strip()]
        self.log(f'schedule set ({len(self.schedule)} entries)')

    async def go(self):
        self.log('started')
        while 1:
            d = datetime.now()
            day, hour, minute = d.weekday(), d.hour, d.minute
            for av in self.schedule:
                if av.day == d.weekday() and av.hour == d.hour and av.minute == d.minute:
                    if not av.triggered:
                        if av.desc == 'WHERE':
                            await self.send_custom(WHERE_IS_THE_VAN, None)
                        else:
                            await self.send_new_van(await self.patch(av.desc), None)
                    av.triggered = True
                else:
                    av.triggered = False
            await asyncio.sleep(1)

    async def patch(self, desc):
        where = await self.backend.discord.where()
        return f'{desc} from lobby 7 (driven from {where})' if where else desc


class Backend():
    def log(self, msg): log('backend', msg)
    def warn(self, msg): log('backend', f'WARN {msg}')

    def __init__(self, debug):
        self.log(f'starting (debug mode: {debug})')
        self.debug = debug
        self.discord = DiscordFrontend(backend=self)
        self.web = WebFrontend(backend=self)
        self.auto = AutoFrontend(backend=self)
        self.frontends = [ 0
                         , self.discord
                         , self.web
                         , self.auto
                         ][1:]
        self.maxvid = 0
        self.vans = []

    def go(self):
        loop = asyncio.get_event_loop()
        for f in self.frontends: loop.create_task(f.go())
        loop.run_forever()

    def save(self):
        with open('db', 'w') as f:
            json.dump({
                'vans': [v.serialize(True) for v in self.vans],
                'whereid': self.discord.whereid
            }, f)

    async def load(self):
        try:
            with open('db') as f:
                data = json.load(f)
                self.vans = [Van.deserialize(v) for v in data['vans']]
                self.maxvid = max((v.vid for v in self.vans), default=-1) + 1
                self.discord.whereid = data['whereid']
                # do this last because it takes time
                for v in self.vans[-5:]:
                    try: v.msg = await self.discord.channel.fetch_message(v.msgid)
                    except discord.errors.NotFound: self.warn(f'van {v.vid} msg not found')
        except FileNotFoundError: pass

    def by_msgid(self, msgid):
        return next((v for v in self.vans if v.msgid == msgid), None)

    def by_vid(self, vid):
        return next((v for v in self.vans if v.vid == vid), None)

    async def send_new_van(self, sender, desc, who):
        self.log(f'new: {sender.label}; {desc}; {who}')
        # TODO error handling, here and below
        if not desc: return self.warn('van with no description?')
        van = Van(self.maxvid, desc, who)
        self.vans.append(van)
        self.maxvid += 1
        await asyncio.gather(*(f.recv_new_van(van) for f in self.frontends))
        self.save()

    async def send_del_van(self, sender, vid):
        self.log(f'del: {sender.label}; {vid}')
        await asyncio.gather(*(f.recv_del_van(vid) for f in self.frontends))
        self.save()

    async def send_hold_van(self, sender, van, who, isadd):
        self.log(f'hold: {sender.label}; {van.vid}; {who}; {isadd}')
        if not who: return self.warn('hold with no holder?')
        if (who in van.holdlist) == isadd: return self.warn('hold with no effect?')
        van.holdlist.append(who) if isadd else van.holdlist.remove(who)
        await asyncio.gather(*(f.recv_update_van(van) for f in self.frontends))
        self.save()

    async def send_custom(self, sender, mtype, data):
        self.log(f'custom: {sender.label}; {mtype}; {repr(data)}')
        await asyncio.gather(*(f.recv_custom(mtype, data) for f in self.frontends))
        self.save()


import sys
Backend('-d' in sys.argv).go()
