#!/usr/bin/env python3

from aiohttp import web
from datetime import datetime
import asyncio
import discord
import json
import random
import re
import subprocess
import os

import sys
isdebug = '-d' in sys.argv
nodebug = lambda x: [] if isdebug else [x]
dd = (lambda f: 'debugdata/'+f) if isdebug else (lambda f: 'data/'+f)
logfile = open(dd('log'), 'a')
def log(label, msg):
    s = f'{datetime.now().strftime("%F %T")} [{label}] {msg}'
    print(s)
    print(s, file=logfile, flush=True)
emd = discord.utils.escape_markdown
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
WHERE_IS_THE_VAN = 0


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
    buses = [ '🚌'
            , '🚐'
            , '🚎'
            , '🚍'
            , '🦈'
            , '🕴️'
            , '✈️'
            ]
    floors = [ [ *nodebug('tichu'), '🐪', '🔂', '☝️' ]
             , [ *nodebug('radiatore'), '💕', '🐫', '🌱', '✌️', '🧦' ]
             , [ *nodebug('bigc'), '🍡', '☘️', '🇮🇲', '🤟' ]
             , [ *nodebug('cflatmajorl'), '🍀', '☠️', '💅', '🦋' ]
             , [ '💫', '🖐️', '🌟', '🇻🇳', '🌿' ]
             , [ '✡️', '❄️', '🌨️', '🔯' ]
             ]
    normal_buses = 4
    places = {
        '🧑‍✈️': 'the lot at 158 mass ave',
        '🇦🇱': 'albany street garage',
        '🗽': 'beneath stata',
        '❓': 'a mystery location'
    }
    coercions = {
        # '🗽': '🇦🇱'
    }
    emojis = {}
    def er(self, e): return self.emojis.get(e, e) # reify
    def ec(self, e): return self.ec2(e if type(e) is str else e.name)
    def ec2(self, e): return self.coercions.get(e, e)

    def uname(self, user): return self.initials.get(user.id, user.display_name)
    async def fmt(self, van):
        return f'van: **{emd(van.desc)}**' + \
            (f' *(by {emd(van.who)})*' if van.who else '') + \
            (f' holding for **{emd(van.holds())}**' if van.holdlist else '')
    async def where(self):
        if not self.whereid: return None
        try:
            wheremsg = await self.channel.fetch_message(self.whereid)
        except:
            return None
        # ugh, python is incompetent and lacks let in comprehensions
        rlist = [(self.places[self.ec(r.emoji)], r.count)
                 for r in wheremsg.reactions
                 if self.ec(r.emoji) in self.places.keys() and r.count > 1]
        gf = lambda emoji: next((i+1 for i,floor in enumerate(self.floors) if self.ec(emoji) in floor), None)
        flist = [(gf(r.emoji), r.count)
                 for r in wheremsg.reactions
                 if gf(r.emoji) and r.count > 1]
        self.log(f'rlist for where: {repr(rlist)}')
        self.whereid = None
        ret = max(rlist, key=lambda x: x[1], default=(self.wheredefault,))[0]
        fl = max(flist, key=lambda x: x[1], default=(None,))[0]
        if fl: ret += f', floor {fl}'
        if len(rlist) == 0: ret += ' (probably)'
        return ret

    def __init__(self, *args, **kwargs):
        Frontend.__init__(self, *args, **kwargs)
        intents = discord.Intents.default()
        intents.members = True
        discord.Client.__init__(self, intents=intents)
        self.silent = self.backend.debug
        self.whereid = None
        self.update_initials()

    async def go(self):
        return await self.start(open(dd('token')).read())

    def update_initials(self):
        self.initials = eval(open(dd('initials')).read())
        return len(self.initials)

    def set_channel(self):
        self.channel = self.channel_debug if self.silent else self.channel_pub

    def set_emojis(self):
        self.emojis = {
            k: v
            for name in 'tichu radiatore bigc cflatmajorl'.split()
            for k,v in [[name, next((x for x in self.channel.guild.emojis if x.name == name), None)]]
            if v
        }
        print(self.emojis)

    async def on_ready(self):
        self.channel_pub = self.get_channel(self.cid_pub)
        self.channel_debug = self.get_channel(self.cid_debug)
        self.set_channel()
        self.set_emojis()
        await self.backend.load()
        self.log('started')

    async def on_message(self, message):
        if message.author == self.user: return

        if message.author.id in self.admin and message.content.startswith('!'):
            cmd, *args = message.content[1:].split(None, 1)
            if hasattr(self, f'admin_{cmd}'):
                await message.channel.send(await getattr(self, f'admin_{cmd}')(args[0] if args else None) or '[done]')
                return

        if re.search(r'(?i)sha+rk', message.content):
            await message.channel.send(f'sh{"a"*random.randint(5,15)}rk')
            return

        if re.search(r'(?i)buf+alo', message.content):
            thing = random.choice(os.listdir('buffalo'))
            await message.channel.send(thing[3:-4].replace('_', ' '), file=discord.File('buffalo/'+thing))

        if m := re.match(r'(?i)roll\s*([-+*/\sd0-9()]+)$', message.content):
            try:
                res = eval(re.sub(r'(\d+)?d(\d+)',
                                  lambda n: str(sum(random.randint(1, int(n.group(2))) for _ in range(int(n.group(1)) if n.group(1) else 1))),
                                  m.group(1)))
            except:
                res = 'no'
            await message.channel.send(res)
            return

        cl = message.content.lower()
        if cl == 'sq' or cl.startswith('sq '):
            args = cl.split()[1:]
            levels = 'mainstream plus a1 a2 c1 c2 c3a c3 c3x c4a c4 c4x all'.split()
            goodnum = lambda x: len(x) == 1 and x in '123456789'
            subprocess.run([ './sq.sh'
                           , ([x for x in args if x in levels]+['C2'])[0]
                           , ([x for x in args if goodnum(x)]+['3'])[0]
                           , 'level' if 'level' in args else 'random'
                           ])
            before = open('sq/before').read()
            after = open('sq/after').read()
            answer = open('sq/answer').read()
            await message.channel.send(f'```{before}```\n```{after}```\n||{answer}||')
            return

        if message.channel.id not in [self.cid_pub, self.cid_debug]: return

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

    async def on_member_update(self, before, after):
        if before.id == 133105865908682752:
            if (bad := next((role for role in before.roles if role.name == 'master-of-the-weird-vacuum'), None)) and bad not in after.roles:
                await after.add_roles(bad, reason='mutiny attempt, is the true master')
        else:
            if bad := next((role for role in after.roles if role.name == 'master-of-the-weird-vacuum'), None):
                await after.remove_roles(bad, reason='impostor, not the true master')

    async def recv_new_van(self, van):
        van.msg = await self.channel.send(await self.fmt(van))
        van.msgid = van.msg.id
        await van.msg.add_reaction(random.choice(
            self.buses[:self.normal_buses] if random.random() < 0.9 else
            self.buses[self.normal_buses:]))

    async def recv_update_van(self, van):
        if van.msg: await van.msg.edit(content=await self.fmt(van))
        else: self.log(f'van {van.vid} tried to update with no msg')

    async def recv_custom(self, mtype, data):
        if mtype == WHERE_IS_THE_VAN:
            self.wheredefault = \
                'the lot at 158 mass ave' if data == 'r' else \
                'albany street garage' if data == 'a' else \
                'beneath stata' if data == 's' else \
                data if data and type(data) is str else '???'
            wheremsg = await self.channel.send(f'where is the van (default: {self.wheredefault})')
            for place in self.places.keys(): await wheremsg.add_reaction(place)
            for floor in self.floors: await wheremsg.add_reaction(self.er(random.choice(floor)))
            self.whereid = wheremsg.id

    async def admin_eval(self, args): return f'```\n{repr(eval(args))}\n```'
    async def admin_await(self, args): return f'```\n{repr(await eval(args))}\n```'
    async def admin_silent(self, args): self.silent = args == '1'; self.set_channel(); return f'silent: {self.silent}'
    async def admin_dump(self, args): return json.dumps([v.serialize() for v in self.backend.vans])
    async def admin_initials(self, args): return f'initials updated ({self.backend.discord.update_initials()} total)'
    async def admin_schedule(self, args):
        if args in ['no', 'none', 'off']:
            self.backend.auto.read_schedule(' ')
        elif args:
            self.backend.auto.read_schedule(None if args == '.' else args)
            return 'new schedule set'
        else:
            return '```\n' + '\n'.join(map(str, self.backend.auto.schedule)) + '\n```'
    async def admin_where(self, args):
        if args == 'clear':
            self.whereid = None
            self.backend.save()
            return 'cleared where'
        else:
            await self.send_custom(WHERE_IS_THE_VAN, args)
            return 'asked where'


class WebFrontend(Frontend):
    label = 'WEB'
    page = lambda *_: re.sub(r'\{\{([^}]*)\}\}', lambda m: open(m.group(1)).read(), open('pardina.html').read())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws = []

    async def fix_ws(self):
        async def subfix(ws):
            if not ws._writer.transport or ws._writer.transport.is_closing():
                await ws.close()
                return False
            return True
        oldlen = len(self.ws)
        self.ws = [ws for ws in self.ws if await subfix(ws)]
        if len(self.ws) < oldlen: self.log(f'fixed websockets x{oldlen - len(self.ws)}')

    async def broadcast(self, msg):
        await self.fix_ws()
        if not self.ws: return
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
        self.schedule = [(lambda a,b,c,d:AutoVan(int(a),int(b),int(c),d))(*line.split(None, 3)) for line in (sched or open(dd('schedule')).read()).split('\n') if line.strip()]
        self.log(f'schedule set ({len(self.schedule)} entries)')

    async def go(self):
        self.log('started')
        while 1:
            d = datetime.now()
            day, hour, minute = d.weekday(), d.hour, d.minute
            for av in self.schedule:
                if av.day == d.weekday() and av.hour == d.hour and av.minute == d.minute:
                    if not av.triggered:
                        if av.desc.startswith('WHERE'):
                            await self.send_custom(WHERE_IS_THE_VAN, av.desc[5:])
                        else:
                            desc, warning = await self.patch(av.desc)
                            # await self.send_new_van(desc, None)
                            # if False and warning: await self.backend.discord.channel.send(f'⚠️🚨⚠️ {warning} 🚨⚠️🚨')
                            if warning: await self.backend.discord.channel.send(warning)
                            await self.send_new_van(desc, None)
                    av.triggered = True
                else:
                    av.triggered = False
            await asyncio.sleep(1)

    async def patch(self, desc):
        where = await self.backend.discord.where()
        prep = '' if where.startswith('beneath') else 'at '
        holds = None if where is None else \
            ', holds between buildings 39 and 24 by default' if 'albany' in where else \
            ', holds at the lot at 158 mass ave by default' if 'lot' in where else ''
        return (f'{desc}{holds}', f'*the van is {prep}{where}*') if where else (desc, None)
        # return (f'{desc} from {where}', holds) if where else (desc, None)


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
        with open(dd('db'), 'w') as f:
            json.dump({
                'vans': [v.serialize(True) for v in self.vans],
                'whereid': self.discord.whereid,
                'wheredefault': self.discord.wheredefault
            }, f)

    async def load(self):
        try:
            with open(dd('db')) as f:
                data = json.load(f)
                self.vans = [Van.deserialize(v) for v in data['vans']]
                self.maxvid = max((v.vid for v in self.vans), default=-1) + 1
                self.discord.whereid = data['whereid']
                self.discord.wheredefault = data['wheredefault']
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


Backend(isdebug).go()
