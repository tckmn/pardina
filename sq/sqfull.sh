#!/usr/bin/env bash
fname="out_$(date +'%F_%T')"
script -qfc "./sqgame.sh $*" "$fname"
clear
grep -B999 -m1 XYZ "$fname" | head -n-3 | tac | grep -B999 -m1 '^ [0-9]\+:' | tac | tail -n+2 > before
tac "$fname" | grep -A999 -m1 $'^ [0-9]\+:' | tail -n+2 | grep -B999 -m1 '^ [0-9]\+:' | tac | tail -n+2 > after
grep '^ [0-9]\+: \+[^ ]' "$fname" | sort | uniq | sed -n '/XYZ/,${s/{ XYZ } //;p}' | tail -n+2 > answer
rm "$fname"
