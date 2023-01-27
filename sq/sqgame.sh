#!/usr/bin/env bash
pwd="$(pwd)"
cd /home/tckmn/misc/sd
printf '[Options]\nno_color\n' > sd.ini
{ echo $1; cat "$pwd/opener"; printf 'insert a comment\nXYZ\n'; for _ in $(seq $2); do printf "pick $3 call\naccept\n"; done; } | timeout -s9 1 ./sdtty
rm sd.ini
