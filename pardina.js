var ws = new WebSocket(window.location.href.replace('http','ws')),
    addvan, updvan;

ws.addEventListener('message', e => {
    var msg = JSON.parse(e.data);
    switch (msg.type) {
    case 'set': msg.vans.forEach(addvan); break;
    case 'add': addvan(msg.van); break;
    case 'upd': updvan(msg.van); break;
    }
});

function elt(tag, txt, opts) {
    opts = opts || {};
    var el = document.createElement(tag);
    el.appendChild(document.createTextNode(txt));
    if (opts.class) el.setAttribute('class', opts.class);
    return el;
}

window.addEventListener('load', () => {
    var nel = document.getElementById('n'),
        nval = localStorage.getItem('n');
    nel.value = nval;
    nel.addEventListener('input', () => localStorage.setItem('n', nval = n.value));

    var vansel = document.getElementById('vans'),
        holdlists = {};

    addvan = van => {
        if (!nval) {
            alert('please set a name');
            return'
        }

        var vel = document.createElement('div');
        holdlists[van.vid] = van.holdlist;

        var btn = document.createElement('button');
        btn.addEventListener('click', () => {
            ws.send(JSON.stringify({
                type: 'hold',
                vid: van.vid,
                who: nval,
                isadd: holdlists[van.vid].indexOf(nval) === -1
            }));
        });
        btn.appendChild(document.createTextNode('hold'));
        vel.appendChild(btn);

        var txt = document.createElement('span');
        txt.appendChild(elt('strong', van.desc));
        if (van.who) txt.appendChild(elt('em', ` (by ${van.who})`));
        txt.appendChild(elt('span', ' holding for ', { class: 'holdfor' }));
        txt.appendChild(elt('strong', van.holdlist.join(', '), { class: 'holdlist' }));
        vel.appendChild(txt);

        vel.setAttribute('id', 'van' + van.vid);
        vel.dataset.hasholds = van.holdlist.length ? 1 : 0;
        vansel.insertBefore(vel, vansel.children[0]);
    };

    updvan = van => {
        if (!nval) {
            alert('please set a name');
            return'
        }

        var vel = document.getElementById('van' + van.vid);
        holdlists[van.vid] = van.holdlist;
        vel.dataset.hasholds = van.holdlist.length ? 1 : 0;
        vel.querySelector('.holdlist').textContent = van.holdlist.join(', ');
    };
});
