var ws;
var endtime = 0;
var em, ec, ee;

function setup() {
    ws = new WebSocket(window.location.href.replace('http','ws'));
    ws.addEventListener('message', em = e => {
        var msg = JSON.parse(e.data);
        if (msg.type !== 'reactor') return;
        endtime = msg.endtime;
        if (msg.explode) document.getElementById('boom').play();
    });

    ws.addEventListener('close', ec = () => {
        setTimeout(setup, 1000);
    });
    ws.addEventListener('error', ee = () => {
        setTimeout(setup, 1000);
    });
}
setup();

function elt(tag, txt, opts) {
    opts = opts || {};
    var el = document.createElement(tag);
    el.appendChild(document.createTextNode(txt));
    if (opts.class) el.setAttribute('class', opts.class);
    return el;
}

window.addEventListener('load', () => {
    document.getElementById('sab').addEventListener('click', () => {
        ws.send(JSON.stringify({ type: 'reactor', action: 'start' }));
    });
    document.getElementById('fix').addEventListener('pointerdown', () => {
        ws.send(JSON.stringify({ type: 'reactor', action: 'press' }));
    });
    document.getElementById('fix').addEventListener('pointerup', () => {
        ws.send(JSON.stringify({ type: 'reactor', action: 'release' }));
    });

    var status = document.getElementById('status');
    var timer = document.getElementById('timer');
    setInterval(() => {
        if (endtime) {
            var left = endtime - (+new Date())/1000;
            if (left < 0) {
                left = 0;
                ws.send(JSON.stringify({ type: 'reactor', action: 'explode' }));
            }
            status.textContent = 'meltdown';
            timer.textContent = left.toFixed(2);
        } else {
            status.textContent = 'OK';
            timer.textContent = '0.00';
        }
    }, 10);
});
